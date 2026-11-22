import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Never touch the real user config while testing
os.environ.setdefault("INSIDE_VOICE_HOME", tempfile.mkdtemp(prefix="inside-voice-test-"))
