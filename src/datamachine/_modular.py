"""Modular Notebooks"""

# AI may not hurt humanity, or, by inaction, allow humanity to come to harm

import glob
import importlib
import json
import os
import shutil
import sys
from datetime import datetime
from urllib.request import urlopen

import psutil

DEFAULT = {
    "number": 1000,
    "folder": "datamachine_temp",
    "library": "benevolent",
    "index": "https://github.com/benevolent-machines/datamachine/blob/master/nb/index.ipynb",
}

CURRENT = {
    "number": DEFAULT["number"],
    "folder": DEFAULT["folder"],
    "library": DEFAULT["library"],
    "index": DEFAULT["index"],
    "process": str(os.getpid()),
    "invoker": None,
    "params": None,
    "notebooks": [],
    "trace": True,
}

def _cache_notebook(notebook):

    if not os.path.exists(CURRENT["folder"]):
        os.makedirs(CURRENT["folder"])

    #print(f"current folder:  {CURRENT['folder']}")
    #print(f"default folder:  {DEFAULT['folder']}")

    if CURRENT["folder"] == DEFAULT["folder"]:
        if CURRENT["invoker"] is None and CURRENT["number"] == DEFAULT["number"]:
            # clear temp files in outer process before first request
            pids = _get_python_pids()
            pattern = f"{CURRENT['folder']}{os.path.sep}d_*"
            for temp_file in glob.glob(pattern):
                pid = temp_file.split("_")[1]
                if pid not in pids:
                    os.remove(temp_file)

    if "temp" not in notebook:  # new entry
        number = CURRENT["number"] = CURRENT["number"] + 1
        file_name = f"d_{CURRENT['process']}_{str(number)}.ipynb"
        file_name = f"{CURRENT['folder']}{os.path.sep}{file_name}"
        notebook["temp"] = file_name

    if notebook["pull"].lower().startswith("https:"):
        with urlopen(notebook["pull"]) as in_url:
            with open(notebook["temp"], "wb") as out_file:
                shutil.copyfileobj(in_url, out_file)

    else:  # it's a file!
        with open(notebook["pull"], encoding="utf-8") as in_file:
            with open(notebook["temp"], "w", encoding="utf-8") as out_file:
                out_file.write(in_file.read())


def _get_notebook(path, library=None, force_reload=False):

    notebook = {}

    # check for a cached entry
    for item in CURRENT["notebooks"]:
        if item["path"] == path:
            notebook = item
            if not force_reload:
                return notebook
            break

    # !! add support for reading notebooks with credentials
    if path.startswith("https://colab"):
        file_id = path.split("/")[-1]  # get the file id
        file_id = file_id.split("?")[0]  # trim out any arguments
        url = "https://docs.google.com/uc?export=download&id="
        url = url + file_id
        notebook["pull"] = url

    elif path.startswith("https://github"):
        url = path.replace("github.com", "raw.githubusercontent.com")
        url = url.replace("/blob/","/")
        notebook["pull"] = url

    elif path.startswith("https:"):
        notebook["pull"] = path

    elif path.endswith(".ipynb"):
        notebook["pull"] = path

    else:  # assume we are left with a library and index to search

        return _lookup_notebook(path, library)

    _cache_notebook(notebook)

    if "path" in notebook:
        notebook["cached"] = True  # already imported

    else:  # new entry
        notebook["cached"] = False  # not yet imported
        notebook["path"] = path
        CURRENT["notebooks"].append(notebook)

    return notebook


def _get_python_pids():
    processes = []
    for process in psutil.process_iter():
        try:
            if "python" in process.name().lower():
                processes.append(str(process.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return processes


def _extract_code(notebook_object):
    code = """
##############################################################################
# Module file generated by datamachine. Any changes here will be lost.       #
##############################################################################
"""
    module_end = False
    for cell in notebook_object["cells"]:
        if cell["cell_type"] == "code":
            src = cell["source"]
            if src[0].startswith("#run"):
                code += "\n# " + "# ".join(cell["source"])
            elif src[0].startswith("#test"):
                code += "\n# " + "# ".join(cell["source"])
            elif src[0].startswith("#module_end") or module_end:
                code += "\n# " + "# ".join(cell["source"])
                module_end = True
            else:
                code += "".join(cell["source"])
        if cell["cell_type"] == "markdown":
            code += "\n# " + "# ".join(cell["source"])
        code += "\n\n"
    return code


def _lookup_notebook(path, library):
    if library is None:
        library = CURRENT["library"]
    if ":" in library or "." in library:  # direct to library
        library_path = library
    else:  # lookup library in index
        index = CURRENT["index"]
        idx = import_notebook(index)
        library_path = idx.LIBRARIES[library]["path"]
    lib = import_notebook(library_path)
    return _get_notebook(lib.NOTEBOOKS[path]["path"])


def _trace(line):
    if CURRENT["trace"] is True:
        path = f"{CURRENT['folder']}{os.path.sep}d_{CURRENT['process']}_trace.txt"
        time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S  ")
        with open(path, "a+", encoding="utf-8") as file_out:
            file_out.write(time_stamp + line + "\n")


def _trace_off():
    CURRENT["trace"] = False


def _trace_on():
    CURRENT["trace"] = True


def _set_home(home):
    """
    Override the home for datamachine_temp folder. 
    The default home is the current directory.
    """
    if len(CURRENT["notebooks"]) > 0:
        print("A set_home() after any import_notebook() will be ignored")
    else:
        if not os.path.isabs(home):
            raise ValueError("Home must be an absolute path.")
        CURRENT["folder"] = os.path.join(home, DEFAULT["folder"])
        if os.path.exists(CURRENT["folder"]):
            shutil.rmtree(CURRENT["folder"])
        os.makedirs(CURRENT["folder"])

def broadcast_modules(spark):
    """\
Import a Python notebook as a module.
    """
    pyfiles = glob.glob(f'{CURRENT["folder"]}/*.py')
    for pyfile in pyfiles:
        spark.sparkContext.addPyFile(pyfile)

def import_notebook(notebook=None, library=None, force_reload=False):
    """\
Import a Python notebook as a module.
    """
    nbo = _get_notebook(notebook, library, force_reload=force_reload)

    nbo["code"] = nbo["temp"].replace("ipynb", "py")
    with open(nbo["temp"], encoding="utf-8") as file_in:
        nbj = json.load(file_in)
        with open(nbo["code"], "w", encoding="utf-8") as code_file:
            code_file.write(_extract_code(nbj))

    # Extract module name and directory from the code file path
    module_name = os.path.basename(nbo["code"]).replace(".py", "")
    module_dir = os.path.dirname(nbo["code"])

    # Insert the module directory at the beginning of sys.path
    original_sys_path = list(sys.path)  # Keep a copy of the original sys.path
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    # Import the module
    importlib.invalidate_caches()
    module = importlib.import_module(module_name)
    if force_reload:
        importlib.reload(module)

    # Restore the original sys.path
    sys.path = original_sys_path

    return module


def set_index(index=None):
    """xxx"""
    # put test here
    if index is None:  # reset to default
        CURRENT["index"] = DEFAULT["index"]
    else:
        CURRENT["index"] = index


def set_library(library=None):
    """xxx"""
    if library is None:
        CURRENT["library"] = DEFAULT["library"]
    else:
        CURRENT["library"] = library


def _show():
    """xxx"""
    # https://colab.research.google.com/drive/1L3l50wwh6M9cK02cFn0dJ0DUVLHEGCcc
    _ = """
    datamachine: https://pypi.org/project/datamachine/
    index:       https://colab.research.google.com/drive/1QE92tEB94X0xLT5AfQf_Hcn1mVK1VkG5
    library:     benevolent - BenevolentMachines.Org
    notebooks:
        dm.execute_notebook('basic',params={"EIN":"987654321"})
        npa = dm.import_notebook('npanalytics') # public nonprofit analytics
        dpa = dm.import_notebook('dpanalytics') # donorperfect analytics
    libraries: 
        dm.set_library("aimee")
        dm.set_library("benevolent")
    """
    #
    print("datamachine https://pypi.org/project/datamachine/\n")
    idx = import_notebook(CURRENT["index"])
    print("idx: " + idx.INDEX + " " + CURRENT["index"])
    if "https:" in CURRENT["library"]:  # direct
        lib = import_notebook(CURRENT["library"])
        print("lib: - " + CURRENT["index"])
    else:  # lookup
        library_path = idx.LIBRARIES[CURRENT["library"]]["path"]
        lib = import_notebook(library_path)
        print("lib: " + CURRENT["library"] + " " + library_path)
    for notebook in lib.NOTEBOOKS:
        print(notebook, lib.NOTEBOOKS[notebook]["path"])
    for notebook in CURRENT["notebooks"]:
        print(notebook["path"])
