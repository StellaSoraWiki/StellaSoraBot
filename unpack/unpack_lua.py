import shutil
import subprocess
import tempfile
from pathlib import Path

from unpack.unpack_paths import data_dir
from unpack.unpack_utils import build_ss_lua_dumper, native_exe


def export_lua():
    dumper_dir = build_ss_lua_dumper()
    dumper = native_exe(dumper_dir / "SSLuaDumper/bin/Debug/net10.0/SSLuaDumper")
    lua_target_dir = Path("assets") / "lua"
    with tempfile.TemporaryDirectory() as work_dir:
        work_dir = Path(work_dir)
        lua_arcx = work_dir / "lua.arcx"
        shutil.copy(data_dir / "Persistent_Store/Scripts/lua.arcx", lua_arcx)
        subprocess.run([dumper.absolute(), lua_arcx], check=True, cwd=dumper_dir)
        lua_source_dir = work_dir / "Lua"
        assert lua_source_dir.exists() and lua_source_dir.is_dir()
        shutil.rmtree(lua_target_dir, ignore_errors=True)
        for f in lua_source_dir.rglob("*.lua"):
            # SSLuaDumper writes Windows paths, which become literal backslashes in file names on Linux
            target = lua_target_dir / str(f.relative_to(lua_source_dir)).replace("\\", "/").lower()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(f, target)


if __name__ == "__main__":
    export_lua()
