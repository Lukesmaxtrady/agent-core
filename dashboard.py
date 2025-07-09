from termcolor import cprint

def main_menu():
    while True:
        cprint("\n" + "="*60, "cyan")
        cprint("SUPERAGENT TERMINAL DASHBOARD".center(60), "cyan", attrs=["bold"])
        cprint("="*60, "cyan")
        print("Welcome! Choose a tool to launch:")
        print("1. LLM Selector & Health Dashboard")
        print("2. Run/Manage Your Apps")
        print("3. Testing & Coverage Tools")
        print("4. Supreme Audit/Auto-Heal")
        print("5. Help & How-To Guides")
        print("6. Exit")
        choice = input("Enter your choice: ").strip()
        if choice == "1":
            import llm_selector_dashboard
            llm_selector_dashboard.main()
        elif choice == "2":
            # You can plug in your app manager here
            cprint("App Manager launching soon...", "yellow")
        elif choice == "3":
            # You can plug in your test tools here
            cprint("Testing tools launching soon...", "yellow")
        elif choice == "4":
            # Plug in your supreme auditor here
            cprint("Supreme Auditor launching soon...", "yellow")
        elif choice == "5":
            from llm_selector_dashboard import help_screen
            help_screen()
        elif choice == "6" or choice.lower() in ("exit", "q"):
            cprint("\nGoodbye!", "cyan")
            break
        else:
            cprint("Invalid choice. Please enter a number from the menu.", "red")

if __name__ == "__main__":
    main_menu()
