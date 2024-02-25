class ConsoleUI:
    # basically move print_finding here
    pass

    # * comment copied from cli.py:
    #! Actually, it's not that simple. I want to show things to the user from the inside of the crawler.
    #! The best idea is probably to (separately from this) create a ui.py file with a UI class (which could
    #! theoretically in the future have different, e.g. GUI implementations), which is then provided to the crawlers.
    #! (-> dependency injection)
    #! this would have to have functions like
    #! display_finding(element: Element, depth: int, first: str, second: str, previous_depth: Optional[int] = None)
    #! indicate_request_started(): print(".", end="")
            # print(".", end="")
            # sys.stdout.flush()  # required to correctly display this in Windows Terminal
    #! and so on
