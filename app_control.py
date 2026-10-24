import subprocess
import os

def open_app(name):
    try:
        os.startfile(name)
    except:
        subprocess.Popen(name, shell=True)

def close_app(name):
    subprocess.run(f"taskkill /f /im {name}.exe", shell=True)
