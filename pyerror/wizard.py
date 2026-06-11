import sys
import os
from pyerror.core import explain
from pyerror.sharing import generate_share_link
from pyerror.report import generate_markdown_report

def debug_wizard():
    """
    Launches an interactive, text-based crash debugger/wizard 
    for the last exception thrown in the REPL session.
    """
    exc = getattr(sys, "last_value", None)
    if exc is None:
        # Check active exception
        _, exc, _ = sys.exc_info()
        
    if exc is None:
        sys.stderr.write("No active or previous exception found to debug.\n")
        return
        
    exc_name = type(exc).__name__
    print("\n" + "="*60)
    print(f"🧠 pyerror Crash Debug Wizard: {exc_name} detected")
    print("="*60)
    
    while True:
        print("\nWhat would you like to do?")
        print("  [1] Translate and explain the error in plain English")
        print("  [2] Print scope variables captured at the crash frame")
        print("  [3] Generate a self-contained base64 error sharing link")
        print("  [4] Save a detailed Markdown triage report to disk")
        print("  [5] Launch the interactive Python debugger (pdb)")
        print("  [6] Exit Wizard")
        
        try:
            choice = input("\nSelect an option [1-6]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Wizard.")
            break
            
        if choice == "1":
            print("\n" + "-"*40)
            explain(exc).show()
            print("-"*40)
        elif choice == "2":
            print("\n" + "-"*40)
            captured = getattr(exc, "__captured_locals__", {})
            if not captured:
                print("No local variables captured. Make sure to use @pyerror.capture_locals or with pyerror.capture_scope().")
            else:
                for scope_name, variables in captured.items():
                    print(f"Scope: {scope_name}")
                    for k, v in variables.items():
                        print(f"  {k} = {v}")
            print("-"*40)
        elif choice == "3":
            print("\n" + "-"*40)
            link = generate_share_link(exc)
            print("Generated Sharing Link:")
            print(link)
            print("-"*40)
        elif choice == "4":
            print("\n" + "-"*40)
            filename = input("Enter report file path [default: error_report.md]: ").strip()
            if not filename:
                filename = "error_report.md"
            try:
                generate_markdown_report(exc, file_path=filename)
                print(f"Markdown report successfully written to: {os.path.abspath(filename)}")
            except Exception as e:
                print(f"Failed to save report: {e}")
            print("-"*40)
        elif choice == "5":
            print("\nLaunching post-mortem pdb session. Type 'q' to quit.")
            print("-"*40)
            import pdb
            tb = getattr(exc, "__traceback__", None)
            if tb:
                pdb.post_mortem(tb)
            else:
                print("No traceback available to start pdb.")
            print("-"*40)
        elif choice == "6" or choice.lower() in ("exit", "quit", "q"):
            print("Exiting Crash Debug Wizard. Happy coding!")
            break
        else:
            print("Invalid option. Please choose a number from 1 to 6.")
