import requests, json, random, sys
from PIL import Image, ImageQt
from dotenv import load_dotenv
from os import getenv
from bs4 import BeautifulSoup
from io import BytesIO
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QGridLayout, QPushButton, QLineEdit
from PyQt5.QtGui import QIcon, QFont, QPixmap
from PyQt5.QtCore import Qt

"""
Game inspired by Cover Quest: https://coverquest.jbonet.xyz/
"""

load_dotenv()
DEFAULT_STEAM_ID = getenv("DEFAULT_STEAM_ID")
STEAM_API_KEY = getenv("STEAM_API_KEY")
default_css = "font-size: 25px; font-family: Arial;"

class Player:
    def __init__(self, steam_id: str):
        if not steam_id and DEFAULT_STEAM_ID is None:
            raise ValueError("You've entered an invalid Steam ID. No default value specified in .env file.")
        elif not steam_id and DEFAULT_STEAM_ID is not None:
            steam_id = DEFAULT_STEAM_ID
        if len(steam_id) != 17 or not steam_id.isalnum():
            raise ValueError(f"You've entered an invalid Steam ID.\nCheck the length and make sure it's alphanumeric.")
        steam_id = steam_id.upper()

        self.steam_id = steam_id
        self.points = 0
        self.player_name = self.get_player_name()
        self.steam_games_ids = self.get_player_steam_games()

    def get_player_name(self) -> str:
        player_info_url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={self.steam_id}&format=json"
        soup = BeautifulSoup(requests.get(player_info_url).text, "html.parser")
        return json.loads(soup.text)['response']['players'][0]['personaname']

    def get_player_steam_games(self) -> list[int]:
        """Given a valid Steam ID, get all the games that the player has"""
        if STEAM_API_KEY is None:
            raise ValueError("No Steam API Key provided in the .env file.")
        player_games_url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={self.steam_id}&format=json"
        soup = BeautifulSoup(requests.get(player_games_url).text, "html.parser")
        try:
            data = json.loads(soup.text)['response']['games']
        except KeyError:
            raise ValueError(f"You've entered an invalid Steam ID. Player ID does not exist.")
        data_ids = [game['appid'] for game in data if game['playtime_forever'] > 30] # Grab game ideas, ignore unplayed games
        # print(json.dumps(data_ids, indent=3))
        return data_ids

    def random_game_id(self) -> int:
        """Simply send one of the player's game ids back"""
        return random.choice(self.steam_games_ids)

    def add_points(self, points: int) -> None:
        self.points += points

class Screenshot:
    def __init__(self, game_id: int):
        self.game_id = game_id
        self.game_name, self.screenshot = self.get_random_game_screenshot()
        self.pixel_size = 25 # Starting pixelation
        self.pixelated_screenshot = self.pixelate_image()

    def get_random_game_screenshot(self) -> tuple[str, Image]:
        """Go the game's Steam page, grab it's title, check its tags, grab a random screenshots and put it in a pillow Image"""
        game_url = f"https://store.steampowered.com/app/{self.game_id}/"
        soup = BeautifulSoup(requests.get(game_url).text, 'html.parser')

        # Do some filtering. Check if the game is actually software.
        game_tags = [tag.get_text().strip() for tag in soup.select('.app_tag')]
        not_a_video_game_tags = ('Utilities','Software','Audio Production','Video Production','Design & Illustration',
                                 'Animation & Modeling','Game Development')
        if any(tag for tag in game_tags if tag in not_a_video_game_tags):
            raise ValueError(f"Found some software that's not actually a video game:{game_tags}")

        name = soup.select_one('#appHubAppName').get_text()
        #Clean up name
        try:
            for grammar in '®™©,:;':
                name = name.replace(grammar, '')
            name = name.title()
        except AttributeError:
            raise ValueError("Found a game that does not have a unique store page (taken off Steam store)")

        # Find the links to the screenshots, grab the high-res version (only visible in pop-up), pick a random one and put it into a Pillow Image
        screenshots = [image['src'] for image in soup.select('img') if f'store_item_assets/steam/apps/{self.game_id}/' in image['src'] and '116x65.' in image['src']]
        random_high_res_link = random.choice(screenshots).replace('116x65','1920x1080')
        random_high_res_link = random_high_res_link[:random_high_res_link.index("?")] #Remove trailing '?t='
        random_screenshot = Image.open(BytesIO(requests.get(random_high_res_link).content)).convert('RGB')

        return name, random_screenshot

    def pixelate_image(self) -> Image:
        """Downsides and the upsizes an Image"""
        small_image = self.screenshot.resize((self.screenshot.width // self.pixel_size, self.screenshot.height // self.pixel_size), Image.BILINEAR)
        pixelated_image = small_image.resize(self.screenshot.size, Image.NEAREST)
        return pixelated_image


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Steam Screenshot Quest!")
        self.setGeometry(700, 300, 800, 800) #Appear roughly in the middle
        self.setWindowIcon(QIcon("icon.png"))

        self.button_submit_id = QPushButton("Submit", self)
        self.entry_steam_id = QLineEdit(self)
        self.label_id_warning_and_welcome = QLabel("Try visiting 'https://www.steamidfinder.com/'",self)
        self.label_screenshot = QLabel(self)
        self.label_score = QLabel("Score: 0", self)
        self.label_hangman = QLabel("_", self)
        self.entry_game_name = QLineEdit(self)
        self.button_game_name = QPushButton("Submit", self)
        self.initUI()

        self.player = None
        self.screenshot = None

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        label_enter_id = QLabel("Enter your 17-Digit Alphanumeric Steam ID", self)
        label_enter_id.setStyleSheet(default_css + "font-weight: bold;")

        self.button_submit_id.clicked.connect(self.submit_steam_id)

        # Image
        pixmap = QPixmap("question_marks.jpg") # Default local value
        self.label_screenshot.setPixmap(pixmap)
        self.label_screenshot.setScaledContents(True)
        #label_screenshot.setGeometry((self.width() - label_screenshot.width()) // 2,100, label_screenshot.width(), label_screenshot.height())



        label_question = QLabel("What is the name of the game this screenshot is from?", self)

        self.label_score.setStyleSheet(default_css + "color: green;")

        self.button_game_name.clicked.connect(self.guess_game_name)

        # Apply generic, repeated traits. Like using a class in CSS
        for x in (label_enter_id, self.label_id_warning_and_welcome, label_question, self.label_score, self.label_hangman):
            x.setAlignment(Qt.AlignCenter)
        for x in (self.entry_steam_id, self.button_submit_id, label_question, self.label_hangman,
                  self.entry_game_name, self.button_game_name, self.label_id_warning_and_welcome):
            x.setStyleSheet(default_css)

        grid = QGridLayout()
        grid.addWidget(label_enter_id, 0, 0, 1, 5)
        grid.addWidget(self.entry_steam_id, 1, 1, 1, 2)
        grid.addWidget(self.button_submit_id, 1, 3)
        grid.addWidget(self.label_id_warning_and_welcome, 2, 0, 1, 5)
        grid.addWidget(self.label_screenshot, 3, 0, 1, 5)
        grid.addWidget(label_question, 4, 0, 1, 4)
        grid.addWidget(self.label_score, 4, 4)
        grid.addWidget(self.label_hangman, 5, 0, 1, 5)
        grid.addWidget(self.entry_game_name, 6, 0, 1, 4)
        grid.addWidget(self.button_game_name, 6, 4)
        central_widget.setLayout(grid)

    def submit_steam_id(self) -> None:
        """Tests for a valid player creation, then either sends back a warning or sets up the game."""
        self.button_submit_id.setDisabled(True)
        self.button_submit_id.setText("Processing...")

        try:
            self.player = Player(steam_id=self.entry_steam_id.text().upper().strip())
        except ValueError as e:
            self.label_id_warning_and_welcome.setStyleSheet(default_css + "color: red;")
            self.label_id_warning_and_welcome.setText(f"Warning: {e}")
            self.button_submit_id.setText("Submit")
            self.button_submit_id.setDisabled(False)
            return
        self.entry_steam_id.setDisabled(True)
        self.button_submit_id.setText("Done!")
        self.label_id_warning_and_welcome.setStyleSheet(default_css + "font-weight: bold;")
        self.label_id_warning_and_welcome.setText(f"Welcome {self.player.player_name}!")


    def set_up_a_screenshot(self) -> None:
        self.screenshot = Screenshot(self.player.random_game_id())

        qt_image = ImageQt(self.screenshot.pixelated_screenshot) # TODO Dies here?

        pixmap = QPixmap.fromImage(qt_image)

        self.label_screenshot.setPixmap(pixmap)
        self.label_screenshot.setScaledContents(True)

        set_up_hangman_spaces = ' '.join(['_' if x != ' ' else ' ' for x in self.screenshot.game_name])
        self.label_hangman.setText(set_up_hangman_spaces)

    def guess_game_name(self):
        pass






def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
