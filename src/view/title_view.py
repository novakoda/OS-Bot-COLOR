import pathlib
import webbrowser as wb

import customtkinter
from PIL import Image, ImageTk

from view.fonts.fonts import *
from view.sprite_scraper_view import SpriteScraperView


class TitleView(customtkinter.CTkFrame):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Spacing
        self.grid_rowconfigure(1, weight=0)  # - Logo
        self.grid_rowconfigure(2, weight=0)  # - Note
        self.grid_rowconfigure(3, weight=0)  # - Buttons
        self.grid_rowconfigure(4, weight=0)  # - Buttons
        self.grid_rowconfigure(5, weight=1)  # Spacing

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=1)

        # Logo
        self.logo_path = pathlib.Path(__file__).parent.parent.resolve()
        self.logo = ImageTk.PhotoImage(
            Image.open(f"{self.logo_path}/images/ui/logo.png").resize((411, 64)),
            Image.ANTIALIAS,
        )
        self.label_logo = customtkinter.CTkLabel(self, image=self.logo, text="", font=body_med_font())
        self.label_logo.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=15, pady=15)

        # Description label
        self.note = "Select a game in the left-side menu to begin."
        self.label_note = customtkinter.CTkLabel(master=self, text=self.note, font=subheading_font())
        self.label_note.bind(
            "<Configure>",
            lambda e: self.label_note.configure(wraplength=self.label_note.winfo_width() - 20),
        )
        self.label_note.grid(row=2, column=0, columnspan=3, sticky="nwes", padx=15, pady=(0, 30))

        # Buttons
        IMG_SIZE = 24
        BTN_WIDTH, BTN_HEIGHT = (96, 64)
        DEFAULT_GRAY = ("gray50", "gray30")

    def btn_github_clicked(self):
        wb.open_new_tab("https://github.com/kelltom/OSRS-Bot-COLOR")

    def btn_feedback_clicked(self):
        wb.open_new_tab("https://github.com/kelltom/OSRS-Bot-COLOR/discussions")

    def btn_bug_report_clicked(self):
        wb.open_new_tab("https://github.com/kelltom/OSRS-Bot-COLOR/issues/new/choose")

    def btn_scraper_clicked(self):
        window = customtkinter.CTkToplevel(master=self)
        window.geometry("400x660")
        window.title("OSRS Wiki Sprite Scraper")
        view = SpriteScraperView(parent=window)
        view.pack(side="top", fill="both", expand=True, padx=20, pady=20)
        window.after(100, window.lift)  # Workaround for bug where main window takes focus
