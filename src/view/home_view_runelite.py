import customtkinter

from view.fonts.fonts import *


class RuneLiteHomeView(customtkinter.CTkFrame):
    def __init__(self, parent, main, game_title: str):
        """
        Creates a new RuneLiteHomeView object.
        Args:
            parent: The parent window.
            main: The main window.
            game_title: The title of the game (E.g., "OSRS").
        """
        super().__init__(parent)
        self.main = main
        self.__game_title = game_title

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Spacing
        self.grid_rowconfigure(1, weight=0)  # - Title
        self.grid_rowconfigure(2, weight=0)  # - Note
        self.grid_rowconfigure(3, weight=0)  # - Warning
        self.grid_rowconfigure(5, weight=0)  # - Status
        self.grid_rowconfigure(6, weight=0)  # - Status
        self.grid_rowconfigure(9, weight=1)  # Spacing

        # Logo
        # self.logo_path = Path(__file__).parent.parent.parent.resolve()
        # self.logo = ImageTk.PhotoImage(Image.open(f"{self.logo_path}/src/images/ui/osrs_logo.png").resize((268, 120), Image.LANCZOS))
        # self.label_logo = customtkinter.CTkLabel(self, image=self.logo)
        # self.label_logo.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=15, pady=15)

        # Title
        self.label_title = customtkinter.CTkLabel(self, text=f"{game_title}", font=title_font())
        self.label_title.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=15, pady=15)

        # Description label
        self.note = (
            "Start the Jagex Launcher and open the OSRS account you want to use. "
            + "Then choose a script from the left panel."
        )
        self.label_note = customtkinter.CTkLabel(master=self, text=self.note, font=body_med_font())
        self.label_note.bind(
            "<Configure>",
            lambda e: self.label_note.configure(wraplength=self.label_note.winfo_width() - 20),
        )
        self.label_note.grid(row=2, column=0, sticky="nwes", padx=15, pady=(0, 15))

        # Warning label
        self.warning = "In your game settings, ensure that status orbs are enabled, shift-drop is enabled, and XP display is set to 'permanent'."
        self.label_warning = customtkinter.CTkLabel(
            master=self,
            text=self.warning,
            font=body_med_font(),
            text_color="orange",
        )
        self.label_warning.bind(
            "<Configure>",
            lambda e: self.label_warning.configure(wraplength=self.label_warning.winfo_width() - 20),
        )
        self.label_warning.grid(row=3, column=0, sticky="nwes", padx=15, pady=(0, 15))

        # Status label
        self.label_status = customtkinter.CTkLabel(master=self, text="", font=body_med_font())
        self.label_status.grid(row=5, column=0, sticky="nwes")
        self.label_status.bind(
            "<Configure>",
            lambda e: self.label_status.configure(wraplength=self.label_status.winfo_width() - 20),
        )

    def __update_label(self, text: str):
        self.label_status.configure(text=text, text_color="white")
