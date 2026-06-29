"""Single source of truth for the app version.

At build time, build.spec reads this and bakes it into the EXE metadata + the
Inno Setup installer filename.  At runtime, the UI and (future) update checker
import it.  The git tag (``v0.9.5``) is the *release* marker; this file is the
*code* marker — bump it, commit, tag, push.
"""

__version__ = "1.0.2"
