"""Main-build entry; corrected retarget implementation is shared with offline QA."""
import runpy,sys,pathlib
sys.argv.append("--main-build")
runpy.run_path(str(pathlib.Path(__file__).with_name("retarget_geometric.py")),run_name="__main__")
