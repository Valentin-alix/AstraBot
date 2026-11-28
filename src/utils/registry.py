import importlib
import os
import sys



def import_proto_modules(folder_path: str) -> None:
    sys.path.append(folder_path)
    for root, _, files in os.walk(folder_path):
        for filename in files:
            if not (filename.endswith(".py") and not filename.startswith("__")):
                continue
            module_name = filename[:-3]
            relative_module_path = os.path.relpath(root, folder_path).replace(os.sep, ".")
            if relative_module_path == ".":
                full_module_name = module_name
            else:
                full_module_name = f"{relative_module_path}.{module_name}"
            importlib.import_module(full_module_name)
