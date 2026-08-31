import subprocess
import sys


def test_fnma_sf_is_import_pure():
    code = (
        "import sys, fnma_sf, fnma_sf.parse, fnma_sf.normalize, fnma_sf.panel,"
        " fnma_sf.collapse, fnma_sf.pipeline;"
        "bad=[m for m in set(sys.modules) if m.split('.')[0] in "
        "{'motor','beanie','pymongo','fastapi','backend'}];"
        "assert not bad, bad; print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
