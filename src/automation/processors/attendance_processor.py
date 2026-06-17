import re
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from src.core.utils import smart_sleep, verify_running
from src.automation.processors.base_processor import BaseProcessor
from src.automation.api_client import SalesforceApiClient
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException
from src.core.logger import logger
from src.core.status_messages import Status

# Excel times are entered in Israel local time; Salesforce datetime fields expect UTC.
_IL_TZ = ZoneInfo("Asia/Jerusalem")
_UTC_TZ = ZoneInfo("UTC")

# Attendance picklist values + the fixed no-action reason. Hardcoded here (the
# automation layer must not import the UI's paste_parser) but kept identical to
# paste_parser.PRESENT/ABSENT so grid values compare and round-trip cleanly.
_PRESENT = "נוכח"
_ABSENT = "לא נוכח"
_NO_ACTION_REASON = "אחר"


def _to_utc_iso(date_str, time_str):
    """Combine an Excel date (YYYY-MM-DD) + time (HH:MM) interpreted as Israel local
    time and return the UTC instant as Salesforce's YYYY-MM-DDTHH:MM:SS.000Z string.
    Uses the Asia/Jerusalem zone so DST (IDT/IST) is handled automatically."""
    local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=_IL_TZ)
    return local.astimezone(_UTC_TZ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utc_to_israel_date(dt_str):
    """Convert a Salesforce UTC datetime string (e.g. '2026-01-18T22:30:00.000Z')
    to the Israel-local calendar date (ISO 'yyyy-mm-dd'). DST-aware, so a session
    late in the UTC day correctly lands on the next Israeli date. Reads only the
    'YYYY-MM-DDTHH:MM:SS' prefix, so trailing '.000Z'/'+00:00' is ignored."""
    dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_UTC_TZ)
    return dt.astimezone(_IL_TZ).strftime("%Y-%m-%d")


def _display_date(iso_date):
    """ISO 'yyyy-mm-dd' → Israeli d.m.yyyy (no leading zeros), matching the grid."""
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{d.day}.{d.month}.{d.year}"


def compute_compare(dates, participants, sf_status_by_date, sf_session_dates, dup_dates, unreported_dates):
    """Pure diff between the grid and Salesforce (no I/O). Returns a findings dict.

    Args:
        dates: grid dates (ISO), the dates the operator entered.
        participants: grid participants ENROLLED in SF (missing ones excluded by
            the caller), each {"id_number", "attendance": {date: status}}.
        sf_status_by_date: {date: {id_number: sf_status_or_None}} for the grid
            dates that map to exactly one SF session (the only comparable ones).
        sf_session_dates: set of all Israel-local dates that have ≥1 SF session.
        dup_dates: set of dates with >1 session (can't be compared unambiguously).
        unreported_dates: set of single-session dates whose session has no reported
            attendance at all (0 rows / all null). They are bucketed as one line
            instead of flooding the report with a "no SF status" mismatch per
            participant. A partially-reported session is NOT here — its individual
            gaps still surface as per-participant mismatches.

    Per grid date, exactly one of: compared (single reported session), unreported
    (single empty session), duplicate, or only-in-grid (no session). A
    per-participant mismatch is grid_status != sf_status.
    """
    grid_dates = set(dates)
    single_sf_dates = sf_session_dates - dup_dates
    findings = {
        "dates_only_grid": sorted(grid_dates - sf_session_dates),
        "dates_only_sf": sorted(sf_session_dates - grid_dates),
        "duplicate_dates": sorted(dup_dates & grid_dates),
        "unreported_dates": sorted(grid_dates & single_sf_dates & unreported_dates),
        "mismatches": [],  # (date, id_number, grid_status, sf_status_or_None)
    }
    for date in sorted((grid_dates & single_sf_dates) - unreported_dates):
        statuses = sf_status_by_date.get(date, {})
        for p in participants:
            idn = p["id_number"]
            grid_status = p["attendance"].get(date)
            sf_status = statuses.get(idn)  # None ⇒ no SD row / null status
            if sf_status != grid_status:
                findings["mismatches"].append((date, idn, grid_status, sf_status))
    return findings


def compute_delta(participants, date, participant_to_delivery, current_status,
                  current_reason, sfdc_participants_map):
    """Pure minimal updateServiceDelivery payload for one session (no I/O).

    Only rows whose status differs from the grid are emitted. ``participants`` are
    already filtered to those enrolled in SF. Returns (records, skipped_id_numbers)
    where skipped lists grid participants that have no Service Delivery row in this
    session (cannot be updated).

    Reason field rules (validated against the manual UI): absent ⇒ reason "אחר";
    present ⇒ reason must be cleared (Salesforce rejects a present row that still
    carries a no-action reason) — but only send the explicit null when a reason is
    actually present, so a fresh/already-present row keeps the exact payload shape
    the existing create flow was validated with (reason key omitted).
    """
    records = []
    skipped = []
    for p in participants:
        idn = p["id_number"]
        sfdc_id = sfdc_participants_map[idn]
        delivery_id = participant_to_delivery.get(sfdc_id)
        if not delivery_id:
            skipped.append(idn)
            continue
        desired = p["attendance"].get(date, _ABSENT)
        if desired == current_status.get(delivery_id):
            continue  # already correct — nothing to send
        record = {"Id": delivery_id, "Pa_Action_Status__c": desired}
        if desired == _ABSENT:
            record["Pa_No_Action_Reason__c"] = _NO_ACTION_REASON
        elif current_reason.get(delivery_id):
            record["Pa_No_Action_Reason__c"] = None  # present ⇒ clear stale reason
        records.append(record)
    return records, skipped


def compute_ambiguous_dates(grid_dates, sessions_by_date):
    """Dates the upsert must NOT write to because the target session is ambiguous:
    the same Israel-local date entered in more than one grid column, or more than
    one existing Salesforce session on that date. These are reported, never written
    — mirroring compare mode and the operator's "report duplicates, don't guess"
    rule. (Without this, two grid columns for one new date would create two
    sessions, since the in-run session lookup isn't re-fetched after a create.)
    """
    dup_in_grid = {d for d in grid_dates if grid_dates.count(d) > 1}
    dup_in_sf = {d for d, ids in sessions_by_date.items() if len(ids) > 1}
    return dup_in_grid | dup_in_sf


# CDP sniffer: steals aura.token/aura.context from Salesforce's own background
# requests so the Aura RPC client (api_client) can reuse the logged-in session.
# Must be injected after _setup_driver() but BEFORE any page loads (login).
_SNIFFER_SCRIPT = """
if (!window.__auraSnifferInjected) {
    window.__sniffedAuraToken = "";
    window.__sniffedAuraContext = "";
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(data) {
        try {
            if (data && typeof data === 'string') {
                var mToken = data.match(/aura\\.token=([^&]+)/);
                if (mToken) window.__sniffedAuraToken = decodeURIComponent(mToken[1]);
                var mContext = data.match(/aura\\.context=([^&]+)/);
                if (mContext && mContext[1].length > 10) window.__sniffedAuraContext = decodeURIComponent(mContext[1]);
            }
        } catch(e) {}
        return origSend.apply(this, arguments);
    };
    var origFetch = window.fetch;
    window.fetch = function() {
        try {
            var body = arguments[1] ? arguments[1].body : null;
            if (body && typeof body === 'string') {
                var mToken = body.match(/aura\\.token=([^&]+)/);
                if (mToken) window.__sniffedAuraToken = decodeURIComponent(mToken[1]);
                var mContext = body.match(/aura\\.context=([^&]+)/);
                if (mContext && mContext[1].length > 10) window.__sniffedAuraContext = decodeURIComponent(mContext[1]);
            }
        } catch(e) {}
        return origFetch.apply(this, arguments);
    };
    window.__auraSnifferInjected = true;
}
"""


class AttendanceProcessor(BaseProcessor):
    """TYPE 3. Dispatches on parm.T3_MODE:
      * "2" — compare only (read-only): diff the grid against existing SF
        attendance and report. Issues ZERO writes (never opens the SD flow).
      * "3" — upsert: create missing sessions, fill/update attendance to match
        the grid (delta only), mirroring the manual UI 1:1.
    """

    def _human_pause(self, min_seconds=1.5, max_seconds=4.0):
        """Sleep a random, human-like interval between Aura API calls so the traffic
        pattern doesn't look like rapid-fire automation. Uses smart_sleep so the pause
        stays interruptible by the stop button."""
        delay = random.uniform(min_seconds, max_seconds)
        smart_sleep(delay, lambda: self.is_stopped)

    def process(self, source):
        mode = str(getattr(parm, "T3_MODE", "2"))
        try:
            # 1. Parent record id from the configured URL.
            match = re.search(r'(?:recordId=|Pa_Service_Schedule__c/)([a-zA-Z0-9]+)', parm.URL)
            if not match:
                raise ValueError("לא ניתן לחלץ recordId מתוך הכתובת המוגדרת ב-config.ini")
            parent_record_id = match.group(1)
            logger.info(f"parent service schedule {parent_record_id} (T3_MODE={mode})", stage="attendance")

            # 2. Pull the attendance matrix from the grid (issue #15/#16).
            excel_data = source.matrix()
            logger.info(
                f"matrix parsed: {len(excel_data['participants'])} participants, "
                f"{len(excel_data['dates'])} dates",
                stage="attendance",
            )
            verify_running(lambda: self.is_stopped)

            # 3. Driver + Aura sniffer (before login) + login.
            self._setup_driver()
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': _SNIFFER_SCRIPT})
            self._login(parm.URL)
            verify_running(lambda: self.is_stopped)
            smart_sleep(5, lambda: self.is_stopped)  # let the page settle so $A is available
            api_client = SalesforceApiClient(self.driver)

            # 4. Participants map (read; shared by both modes): id number → SF id.
            sfdc_participants_map = api_client.get_participants(parent_record_id)
            logger.info(f"participants fetched: {len(sfdc_participants_map)}", stage="aura")
            verify_running(lambda: self.is_stopped)

            if mode == "3":
                return self._run_upsert(api_client, parent_record_id, excel_data, sfdc_participants_map)
            return self._run_compare(api_client, parent_record_id, excel_data, sfdc_participants_map)

        finally:
            # StopRequestedException and genuine failures propagate to the worker;
            # we only own the driver lifecycle here. Neither mode keeps the browser
            # open (no handoff), so the worker closes Chrome on every exit path.
            self._cleanup_driver()

    # ---------------------------------------------------------------- shared
    def _split_participants(self, excel_data, sfdc_participants_map):
        """Return (valid, missing_ids, sf_only_ids):
          * valid       — grid participants enrolled in SF (preserves grid order),
          * missing_ids — grid IDs not enrolled in the course,
          * sf_only_ids — course participants absent from the grid.
        """
        missing_ids, valid = [], []
        for p in excel_data["participants"]:
            if p["id_number"] in sfdc_participants_map:
                valid.append(p)
            else:
                missing_ids.append(p["id_number"])
        grid_ids = {p["id_number"] for p in excel_data["participants"]}
        sf_only_ids = [idn for idn in sfdc_participants_map if idn not in grid_ids]
        return valid, missing_ids, sf_only_ids

    def _sessions_by_date(self, sessions):
        """Map Israel-local date (ISO) → list of session ids. Sessions with an
        unparseable/empty start datetime are skipped (and logged)."""
        by_date = {}
        for s in sessions:
            start = s.get("start_utc")
            if not start:
                continue
            try:
                d = _utc_to_israel_date(start)
            except Exception:
                logger.warning(f"session {s.get('id')} has unparseable start '{start}' — skipped", stage="aura")
                continue
            by_date.setdefault(d, []).append(s["id"])
        return by_date

    # --------------------------------------------------------- mode 2: compare
    def _run_compare(self, api_client, parent_record_id, excel_data, sfdc_participants_map):
        """Read-only: diff the grid against existing SF attendance. ZERO writes —
        reads sessions + Service Delivery rows via related lists, never the flow."""
        valid, missing_ids, sf_only_ids = self._split_participants(excel_data, sfdc_participants_map)

        # Human-like pause mimics opening the "מפגשים" tab. Read-only mode still
        # paces its Aura calls like the upsert path so the traffic never looks like
        # rapid-fire automation (a burst of reads can trip Salesforce's bot/security
        # heuristics just like writes).
        self._human_pause(1.5, 3.0)
        sessions = api_client.get_sessions(parent_record_id)
        logger.info(f"sessions fetched: {len(sessions)}", stage="aura")
        verify_running(lambda: self.is_stopped)

        sessions_by_date = self._sessions_by_date(sessions)
        sf_session_dates = set(sessions_by_date)
        dup_dates = {d for d, ids in sessions_by_date.items() if len(ids) > 1}

        # participant SF id → grid id number, to translate SD rows back to IDs.
        rev = {v: k for k, v in sfdc_participants_map.items()}

        grid_dates = set(excel_data["dates"])
        compare_dates = sorted(grid_dates & (sf_session_dates - dup_dates))
        sf_status_by_date = {}
        unreported_dates = set()
        total = len(compare_dates)
        for idx, date in enumerate(compare_dates):
            verify_running(lambda: self.is_stopped)
            logger.set_context(stage="aura", date=date)
            self.update_ui(status=Status.t3_cmp_processing(_display_date(date), idx + 1, total))
            # Pace each per-session read like a human opening a session and viewing
            # its attendance (interruptible by Stop via smart_sleep).
            self._human_pause(2.0, 4.0)
            deliveries = api_client.get_service_deliveries(sessions_by_date[date][0])
            statuses = {}
            for d in deliveries:
                idn = rev.get(d["participant"])
                if idn:
                    statuses[idn] = d["status"]
            sf_status_by_date[date] = statuses
            # A session with no row carrying a real status is "exists but never
            # reported" — bucket it as one line rather than a "not reported"
            # mismatch per participant.
            if not any(d["status"] for d in deliveries):
                unreported_dates.add(date)
        logger.reset_context()

        findings = compute_compare(
            excel_data["dates"], valid, sf_status_by_date, sf_session_dates, dup_dates, unreported_dates
        )
        mismatches = findings["mismatches"]
        n_diffs = (
            len(findings["dates_only_grid"]) + len(findings["dates_only_sf"])
            + len(findings["duplicate_dates"]) + len(findings["unreported_dates"])
            + len(mismatches) + len(missing_ids) + len(sf_only_ids)
        )
        logger.info(f"compare complete: {n_diffs} differences", stage="run")

        summary = {"success_text": Status.t3_cmp_summary(n_diffs)}
        sections = []
        if findings["dates_only_grid"]:
            sections.append({"title": Status.cmp_dates_only_grid_title(len(findings["dates_only_grid"])),
                             "ids": [_display_date(d) for d in findings["dates_only_grid"]]})
        if findings["unreported_dates"]:
            sections.append({"title": Status.cmp_unreported_dates_title(len(findings["unreported_dates"])),
                             "ids": [_display_date(d) for d in findings["unreported_dates"]]})
        if findings["dates_only_sf"]:
            sections.append({"title": Status.cmp_dates_only_sf_title(len(findings["dates_only_sf"])),
                             "ids": [_display_date(d) for d in findings["dates_only_sf"]]})
        if findings["duplicate_dates"]:
            sections.append({"title": Status.cmp_duplicate_dates_title(len(findings["duplicate_dates"])),
                             "ids": [_display_date(d) for d in findings["duplicate_dates"]]})
        if mismatches:
            sections.append({"title": Status.cmp_mismatch_title(len(mismatches)),
                             "lines": [Status.cmp_mismatch_line(_display_date(d), idn, gs, ss)
                                       for (d, idn, gs, ss) in mismatches]})
        if missing_ids:
            sections.append({"title": Status.cmp_missing_ids_title(len(missing_ids)),
                             "ids": [str(x) for x in missing_ids]})
        if sf_only_ids:
            sections.append({"title": Status.cmp_sf_only_title(len(sf_only_ids)),
                             "ids": [str(x) for x in sf_only_ids]})
        if sections:
            summary["sections"] = sections

        self.update_ui(status=Status.t3_cmp_done(n_diffs), level=("success" if n_diffs == 0 else "warning"))
        return summary

    def _apply_via_flow(self, api_client, session_id, date, valid, sfdc_participants_map):
        """Reconcile one session to the grid via the proven 1:1 manual sequence:
        open the SD flow (creating any missing rows), push only the changed rows,
        then finish the flow (so its side-effects, e.g. Program Engagement
        activation, run). Used for new sessions and for existing ones that differ."""
        self._human_pause(1.5, 3.5)
        serialized_state, delivery_records = api_client.start_create_sd_flow(session_id)

        participant_to_delivery, current_status, current_reason = {}, {}, {}
        for rec in delivery_records:
            pid, did = rec.get("Pa_Service_Participant__c"), rec.get("Id")
            if pid and did:
                participant_to_delivery[pid] = did
                current_status[did] = rec.get("Pa_Action_Status__c")
                current_reason[did] = rec.get("Pa_No_Action_Reason__c")

        records, skipped = compute_delta(
            valid, date, participant_to_delivery, current_status, current_reason, sfdc_participants_map
        )
        if skipped:
            logger.warning(f"{len(skipped)} grid participants have no SD row on {date} — skipped", stage="aura", date=date)

        verify_running(lambda: self.is_stopped)
        if records:
            # Human-like pause scaled to the number of rows being marked (capped).
            n = len(records)
            self._human_pause(min(3.0 + n * 0.3, 30.0), min(6.0 + n * 0.7, 45.0))
            api_client.report_attendance(records)
            logger.debug(f"report_attendance → {n} changed", stage="aura", date=date)
        else:
            logger.debug("no attendance changes", stage="aura", date=date)

        verify_running(lambda: self.is_stopped)
        # Finish the flow (== manual "save"), mirroring the HAR, so its
        # post-processing side-effects (e.g. Program Engagement activation) run.
        self._human_pause(1.5, 3.0)
        api_client.finish_create_sd_flow(serialized_state, delivery_records)
        logger.debug("finish_create_sd_flow done", stage="aura", date=date)

    # ---------------------------------------------------------- mode 3: upsert
    def _run_upsert(self, api_client, parent_record_id, excel_data, sfdc_participants_map):
        """Reconcile Salesforce attendance to the grid. Per date: create a missing
        session and fill it; for an existing session, READ its attendance first
        (read-only) and only open the SD flow when something must be created or
        changed — a date that already matches the grid is left untouched (no write).
        Each write path is the proven 1:1 manual sequence (see _apply_via_flow)."""
        valid, missing_ids, sf_only_ids = self._split_participants(excel_data, sfdc_participants_map)
        if not valid:
            raise ValueError("אף אחד ממספרי הזהות בגריד לא נמצא ברשימת המשתתפים בפעילות.")

        sessions = api_client.get_sessions(parent_record_id)
        logger.info(f"sessions fetched: {len(sessions)}", stage="aura")
        verify_running(lambda: self.is_stopped)
        sessions_by_date = self._sessions_by_date(sessions)

        grid_dates = excel_data["dates"]
        total_dates = len(grid_dates)
        ambiguous = compute_ambiguous_dates(grid_dates, sessions_by_date)
        created = updated = unchanged = 0
        duplicate_dates = []
        seen = set()

        for idx, date in enumerate(grid_dates):
            verify_running(lambda: self.is_stopped)
            logger.set_context(stage="aura", date=date)
            self.update_ui(status=Status.t3_processing(_display_date(date), idx + 1, total_dates))

            if date in seen:
                continue  # same date in another grid column — already handled
            seen.add(date)

            on_date = sessions_by_date.get(date, [])
            if date in ambiguous:
                # Ambiguous target (duplicate grid column or >1 SF session): write
                # nothing, report it. Guards against creating a second session for a
                # date repeated across grid columns.
                logger.warning(
                    f"date {date} ambiguous (grid×{grid_dates.count(date)}, SF sessions×{len(on_date)}) — skipped",
                    stage="aura", date=date,
                )
                duplicate_dates.append(date)
                continue

            if not on_date:
                # New date → create the session, then fill it via the flow (which
                # creates the per-participant rows). New rows always need writing.
                self._human_pause(2.0, 4.5)
                start_utc = _to_utc_iso(date, excel_data["start_time"])
                end_utc = _to_utc_iso(date, excel_data["end_time"])
                session_id = api_client.create_session(parent_record_id, start_utc, end_utc)
                created += 1
                logger.debug(f"create_session → {session_id}", stage="aura", date=date)
                verify_running(lambda: self.is_stopped)
                self._apply_via_flow(api_client, session_id, date, valid, sfdc_participants_map)
                continue

            # Existing session → READ its attendance first (read-only) and decide.
            # Only open the flow if a row is missing or a status differs; a date that
            # already matches the grid is left untouched, so a bulk run writes only
            # to the dates that actually differ.
            session_id = on_date[0]
            self._human_pause(1.5, 3.0)
            deliveries = api_client.get_service_deliveries(session_id)
            p2d = {d["participant"]: d["id"] for d in deliveries if d["participant"] and d["id"]}
            cur_status = {d["id"]: d["status"] for d in deliveries}
            cur_reason = {d["id"]: d["reason"] for d in deliveries}
            pre_records, pre_skipped = compute_delta(
                valid, date, p2d, cur_status, cur_reason, sfdc_participants_map
            )
            if not pre_records and not pre_skipped:
                # Every grid participant already has a matching row — nothing to do.
                unchanged += 1
                logger.debug("already matches grid — no write", stage="aura", date=date)
                continue

            verify_running(lambda: self.is_stopped)
            self._apply_via_flow(api_client, session_id, date, valid, sfdc_participants_map)
            updated += 1

        logger.reset_context()
        logger.info(f"upsert complete: {created} created, {updated} updated, {unchanged} unchanged", stage="run")

        summary = {"success_text": Status.t3_upsert_summary(created, updated, unchanged)}
        sections = []
        if duplicate_dates:
            sections.append({"title": Status.cmp_duplicate_dates_title(len(duplicate_dates)),
                             "ids": [_display_date(d) for d in duplicate_dates]})
        if sf_only_ids:
            sections.append({"title": Status.cmp_sf_only_title(len(sf_only_ids)),
                             "ids": [str(x) for x in sf_only_ids]})
        if sections:
            summary["sections"] = sections

        self.update_ui(status=Status.t3_upsert_done(created, updated, unchanged), level="success")
        if missing_ids:
            self.update_ui(status=Status.t3_missing(missing_ids), level="warning")
            summary["problems_title"] = Status.missing_ids_title(len(missing_ids))
            summary["problem_ids"] = [str(x) for x in missing_ids]
        return summary


# --------------------------------------------------------------- self-check
# Runnable (no framework, no network/driver):
#   python -m src.automation.processors.attendance_processor
# Guards the pure logic: timezone-aware date matching and the compare/delta
# computations — the parts that decide what gets read, reported, and changed.
if __name__ == "__main__":
    # _utc_to_israel_date: winter (UTC+2) and summer (UTC+3) incl. cross-midnight.
    assert _utc_to_israel_date("2026-01-18T12:18:15.000Z") == "2026-01-18"
    assert _utc_to_israel_date("2026-01-18T22:30:00.000Z") == "2026-01-19"  # +2 → next day
    assert _utc_to_israel_date("2026-06-17T22:30:00.000Z") == "2026-06-18"  # +3 → next day
    assert _display_date("2026-01-18") == "18.1.2026"

    parts = [
        {"id_number": "111111111", "attendance": {"2026-01-18": _PRESENT, "2026-01-19": _ABSENT, "2026-01-20": _PRESENT}},
        {"id_number": "222222222", "attendance": {"2026-01-18": _ABSENT, "2026-01-19": _ABSENT, "2026-01-20": _PRESENT}},
    ]
    # d18 single session (comparable), d19 duplicate, d20 no session; SF also has d99 (extra).
    sf_status_by_date = {"2026-01-18": {"111111111": _PRESENT, "222222222": _PRESENT}}  # 222 differs (grid ABSENT)
    cmp = compute_compare(
        ["2026-01-18", "2026-01-19", "2026-01-20"], parts, sf_status_by_date,
        sf_session_dates={"2026-01-18", "2026-01-19", "2026-01-99"}, dup_dates={"2026-01-19"},
        unreported_dates=set(),
    )
    assert cmp["dates_only_grid"] == ["2026-01-20"], cmp
    assert cmp["dates_only_sf"] == ["2026-01-99"], cmp
    assert cmp["duplicate_dates"] == ["2026-01-19"], cmp
    assert cmp["unreported_dates"] == [], cmp
    assert cmp["mismatches"] == [("2026-01-18", "222222222", _ABSENT, _PRESENT)], cmp

    # mismatch where SF has no row for a participant → sf_status None.
    cmp2 = compute_compare(["2026-01-18"], parts, {"2026-01-18": {"111111111": _PRESENT}},
                           sf_session_dates={"2026-01-18"}, dup_dates=set(), unreported_dates=set())
    assert cmp2["mismatches"] == [("2026-01-18", "222222222", _ABSENT, None)], cmp2

    # fully-unreported session → bucketed as one date, NOT a mismatch per participant.
    cmp3 = compute_compare(["2026-01-18"], parts, {"2026-01-18": {}},
                           sf_session_dates={"2026-01-18"}, dup_dates=set(),
                           unreported_dates={"2026-01-18"})
    assert cmp3["unreported_dates"] == ["2026-01-18"], cmp3
    assert cmp3["mismatches"] == [], cmp3  # no per-participant flood

    # compute_delta: status mapping, reason rules, change detection, skip.
    pmap = {"111111111": "P1", "222222222": "P2", "333333333": "P3"}
    p2d = {"P1": "D1", "P2": "D2"}  # P3 has no delivery row → skipped
    dparts = [
        {"id_number": "111111111", "attendance": {"d": _PRESENT}},  # was ABSENT+reason → present, clear reason
        {"id_number": "222222222", "attendance": {"d": _ABSENT}},   # was PRESENT → absent + reason "אחר"
        {"id_number": "333333333", "attendance": {"d": _PRESENT}},  # no row → skipped
    ]
    recs, skipped = compute_delta(
        dparts, "d", p2d,
        current_status={"D1": _ABSENT, "D2": _PRESENT},
        current_reason={"D1": _NO_ACTION_REASON, "D2": None},
        sfdc_participants_map=pmap,
    )
    by_id = {r["Id"]: r for r in recs}
    assert by_id["D1"] == {"Id": "D1", "Pa_Action_Status__c": _PRESENT, "Pa_No_Action_Reason__c": None}, by_id
    assert by_id["D2"] == {"Id": "D2", "Pa_Action_Status__c": _ABSENT, "Pa_No_Action_Reason__c": _NO_ACTION_REASON}, by_id
    assert skipped == ["333333333"], skipped

    # No-op when already correct; fresh present row omits the reason key.
    recs2, _ = compute_delta(
        [{"id_number": "111111111", "attendance": {"d": _PRESENT}}], "d", {"P1": "D1"},
        current_status={"D1": _PRESENT}, current_reason={"D1": None}, sfdc_participants_map={"111111111": "P1"},
    )
    assert recs2 == [], recs2  # unchanged → nothing sent
    recs3, _ = compute_delta(
        [{"id_number": "111111111", "attendance": {"d": _PRESENT}}], "d", {"P1": "D1"},
        current_status={"D1": None}, current_reason={"D1": None}, sfdc_participants_map={"111111111": "P1"},
    )
    assert recs3 == [{"Id": "D1", "Pa_Action_Status__c": _PRESENT}], recs3  # fresh → present, no reason key

    # compute_ambiguous_dates: duplicate grid column OR >1 SF session ⇒ ambiguous.
    amb = compute_ambiguous_dates(
        ["2026-05-20", "2026-05-20", "2026-05-21", "2026-05-22"],
        {"2026-05-21": ["s1"], "2026-05-22": ["s2", "s3"]},
    )
    assert amb == {"2026-05-20", "2026-05-22"}, amb  # 20 dup-in-grid, 22 dup-in-SF, 21 fine

    print("OK — attendance_processor pure logic (date matching, compare, delta, ambiguity)")
