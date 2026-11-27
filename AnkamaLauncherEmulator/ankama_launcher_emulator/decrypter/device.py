import getpass
import hashlib
import math
import os
import platform
import subprocess
from pathlib import Path

import psutil

import pythoncom
from winerror import RPC_E_CHANGED_MODE
from win32com.client import GetObject


class Device:
    __uuid: str | None = None

    @staticmethod
    def getUUID() -> str:
        if Device.__uuid:
            return Device.__uuid

        plt = Device.getPlatform()
        arch = Device.getArch()
        machine_id = Device.getMachineId(arch)
        cpu_count = Device.getCpuLength()
        cpu_model = Device.getCpuModel()

        Device.__uuid = ",".join([plt, arch, machine_id, str(cpu_count), cpu_model])
        return Device.__uuid

    @staticmethod
    def getMachineId(arch: str, original: bool = False) -> str:
        try:
            machine_uuid = Device.getMachineGuid(arch)

            if original:
                return machine_uuid

            sha256_hash_machine_uuid = hashlib.sha256()
            sha256_hash_machine_uuid.update(machine_uuid.encode("utf-8"))
            return sha256_hash_machine_uuid.hexdigest()
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("Error while obtaining machine id: " + str(error)) from error

    @staticmethod
    def getMachineGuid(arch: str) -> str:
        reg_exe = Device.getWindowsRegExecutable(arch)
        output = subprocess.check_output(
            [
                str(reg_exe),
                "QUERY",
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography",
                "/v",
                "MachineGuid",
            ],
            text=True,
            encoding="locale",
            timeout=10,
        )
        return "".join(output.split("REG_SZ")[1].split()).lower()

    @staticmethod
    def getWindowsRegExecutable(arch: str) -> Path:
        windows_dir = Path(os.environ.get("windir", r"C:\Windows"))
        system_dir = "sysnative" if arch == "x86" and "PROCESSOR_ARCHITEW6432" in os.environ else "System32"
        return windows_dir / system_dir / "REG.exe"

    @staticmethod
    def getArch() -> str:
        arch_map = {"AMD64": "x64", "x86_64": "x64", "i386": "x86", "i686": "x86"}
        machine = platform.machine()
        if machine not in arch_map:
            raise OSError(f"Unsupported architecture: {machine}")
        return arch_map[machine]

    @staticmethod
    def getPlatform() -> str:
        return "win32"

    @staticmethod
    def getCpuLength() -> int:
        return psutil.cpu_count(logical=True) or 0

    @staticmethod
    def getCpuModel() -> str:
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except pythoncom.com_error as error:
            if error.hresult != RPC_E_CHANGED_MODE:
                raise
            initialized_here = False
        else:
            initialized_here = True
        try:
            name = next(iter(GetObject(r"winmgmts:root\cimv2").ExecQuery("SELECT Name FROM Win32_Processor"))).Name
            if not isinstance(name, str):
                raise RuntimeError("WMI returned a non-string processor name")
            return name
        finally:
            if initialized_here:
                pythoncom.CoUninitialize()

    @staticmethod
    def getComputerRam() -> int:
        ram_mb = int(psutil.virtual_memory().total / (1024**2))
        return int(2 ** round(math.log(ram_mb, 2)))

    @staticmethod
    def getOsVersion() -> float:
        version_splitted = platform.version().split(".")
        major_version = version_splitted[0]
        medium_version = version_splitted[1]
        return float(f"{major_version}.{medium_version}")

    @staticmethod
    def getUsername() -> str:
        return getpass.getuser()
