"""LayerForge: pallet layer patterns from PDF to symbolic PLC parameters."""

APP_NAME = "LayerForge"

# AUTOBUILD.py writes build_version.py next to run.py for every build. A source
# checkout has none: the version is then "dev".
try:
    import build_version as _build
    APP_VERSION, BUILD_TIME, COMMIT_URL = _build.VERSION, _build.BUILD_TIME, _build.COMMIT_URL
except ImportError:
    APP_VERSION, BUILD_TIME, COMMIT_URL = "dev", "", ""
