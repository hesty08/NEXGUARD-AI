"""Isolasi pengujian: database sementara dan direktori kerja = folder proyek."""
import os, sys, tempfile
os.environ["CYBERSHIELD_DB"] = os.path.join(tempfile.mkdtemp(prefix="cs_test_"), "test.db")
os.environ.pop("FACTCHECK_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
