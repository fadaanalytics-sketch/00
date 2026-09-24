"""Run the backend locally against a folder standing in for Google Drive.

For development and testing only - the real thing runs inside Colab via the notebook.
    python colab/run_local.py --drive /path/to/fake-drive [--port 8000]
"""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive", required=True, help="folder that plays the role of MyDrive")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    drive = os.path.abspath(args.drive)
    os.environ.setdefault("AVA_MOUNT_ROOT", drive)
    os.environ.setdefault("AVA_WORK_DIR", os.path.join(os.path.dirname(drive), "ava_work"))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import uvicorn
    uvicorn.run("ava.server:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
