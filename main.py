import requests, json, random, sys, io, roman, re
from PIL import Image
from dotenv import load_dotenv
from os import getenv
from bs4 import BeautifulSoup
from io import BytesIO
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QGridLayout, QPushButton, QLineEdit
from PyQt5.QtGui import QIcon, QFont, QPixmap, QImage
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
            raise ValueError(f"You've entered an invalid Steam ID.\nCheck the length and make sure it's numeric.")
        steam_id = steam_id.upper()

        self.steam_id = steam_id
        self.points = 0
        self.player_name = self.get_player_name()
        self.steam_games_ids = self.get_player_steam_games()

    def get_player_name(self) -> str:
        # TODO What if the Steam Account is set to private?
        player_info_url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={self.steam_id}&format=json"
        soup = BeautifulSoup(requests.get(player_info_url).text, "html.parser")
        try:
            return json.loads(soup.text)['response']['players'][0]['personaname']
        except Exception:
            raise ValueError("Could not talk to the Steam API. Is your key valid/correct?")


    def get_player_steam_games(self) -> list[int]:
        """Given a valid Steam ID, get all the games that the player has"""
        if STEAM_API_KEY is None:
            raise ValueError("No Steam API Key provided in the .env file.")
        player_games_url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={self.steam_id}&format=json"
        soup = BeautifulSoup(requests.get(player_games_url).text, "html.parser")
        try:
            data = json.loads(soup.text)['response']['games']
        except KeyError:
            raise ValueError(f"You've entered an invalid Steam ID. Player ID does not exist.") # Already tested for valid API in get_player_name
        data_ids = [game['appid'] for game in data if game['playtime_forever'] > 15] # Grab game ideas, ignore unplayed games
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
        # Keep trying to get the name and normal_screenshot. Don't leave until you do.
        while True:
            try:
                self.game_name, self.normal_screenshot = self.get_random_game_screenshot()
                break
            except ValueError:
                pass
        self.pixel_size = 35 # Starting pixelation, dropped by -5 during setup
        self.first_turn = True #Required for hinting hangman length after the first chance to guess it
        self.solved = False
        self.pixelated_screenshot = None
        self.pixelate_image() # Setups up the pixelated screenshot

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
            for grammar in '®™©,.:;?\'"-()[]{}':
                name = name.replace(grammar, '')
            name = remove_roman_numerals(name)
            name = name.title()
            for edition in ('Game Of The Year Edition','Definitive Edition','Complete Edition'):
                name = name.replace(edition, '')
            name = name.strip()
        except AttributeError:
            raise ValueError("Found a game that does not have a unique store page (taken off Steam store)")

        # Find the links to the screenshots, grab the high-res version (only visible in pop-up), pick a random one and put it into a Pillow Image
        screenshots = [image['src'] for image in soup.select('img') if f'store_item_assets/steam/apps/{self.game_id}/' in image['src'] and '116x65.' in image['src']]
        random_high_res_link = random.choice(screenshots).replace('116x65','1920x1080')
        random_high_res_link = random_high_res_link[:random_high_res_link.index("?")] #Remove trailing '?t='
        random_screenshot = Image.open(BytesIO(requests.get(random_high_res_link).content))

        return name, random_screenshot

    def pixelate_image(self) -> None:
        """Downsides and the upsizes an Image"""
        self.pixel_size -= 5
        if self.pixel_size < 1:
            self.pixel_size = 1
        small_image = self.normal_screenshot.resize((self.normal_screenshot.width // self.pixel_size, self.normal_screenshot.height // self.pixel_size), Image.BILINEAR)
        pixelated_image = small_image.resize(self.normal_screenshot.size, Image.NEAREST)
        self.pixelated_screenshot = pixelated_image


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Steam Screenshot Quest!")
        self.setGeometry(700, 300, 800, 800) #Appear roughly in the middle
        self.setWindowIcon(QIcon("icon.png"))

        self.button_submit_id = QPushButton("Submit", self)
        self.entry_steam_id = QLineEdit(self)
        self.label_id_warning_and_welcome = QLabel('Try visiting "https://www.steamidfinder.com/"',self)
        self.label_screenshot = QLabel(self)
        self.label_score = QLabel("Score: 0", self)
        self.label_hangman = QLabel("", self)
        self.entry_game_name = QLineEdit(self)
        self.button_game_name = QPushButton("Submit", self)
        self.initUI()

        self.player = None
        self.screenshot = None

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        label_enter_id = QLabel("Enter your 17-Digit Steam ID", self)
        label_enter_id.setStyleSheet(default_css + "font-weight: bold;")

        self.button_submit_id.clicked.connect(self.submit_steam_id)

        # Image
        pixmap = QPixmap("question_marks.jpg") # Default local value
        scaled_pixmap = pixmap.scaled(720, 480, Qt.KeepAspectRatio)
        self.label_screenshot.setPixmap(scaled_pixmap)
        self.label_screenshot.setScaledContents(True)
        #label_screenshot.setGeometry((self.width() - label_screenshot.width()) // 2,100, label_screenshot.width(), label_screenshot.height())


        label_question = QLabel("What is the name of the game this screenshot is from?", self)

        self.label_score.setStyleSheet(default_css + "color: green;")

        self.entry_game_name.setDisabled(True)

        self.button_game_name.clicked.connect(self.guess_game_name)
        self.button_game_name.setDisabled(True)

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
        try:
            self.player = Player(steam_id=self.entry_steam_id.text().upper().strip())
        except ValueError as e:
            self.label_id_warning_and_welcome.setStyleSheet(default_css + "color: red;")
            self.label_id_warning_and_welcome.setText(f"Warning: {e}")
            return
        player_username = self.player.player_name
        print(f'Created player "{player_username}"')
        self.entry_steam_id.setDisabled(True)
        self.button_submit_id.setText("")
        self.button_submit_id.setDisabled(True)
        self.label_id_warning_and_welcome.setStyleSheet(default_css + "font-weight: bold;")
        self.label_id_warning_and_welcome.setText(f"Welcome {player_username}!")

        self.entry_game_name.setDisabled(False)
        self.button_game_name.setDisabled(False)

        self.set_up_a_screenshot()

    def set_up_a_screenshot(self) -> None:
        """Create a new screenshot, display it, and clear the text entry box"""
        self.screenshot = Screenshot(self.player.random_game_id())
        print(f"The answer is {self.screenshot.game_name}") #Debugging

        self.display_screenshot(pixelated=True)

        # Clear text for proceeding rounds
        self.entry_game_name.setText("")
        self.label_hangman.setText("")
        self.button_game_name.setText("Submit")

    def display_screenshot(self, pixelated: bool) -> None:
        """Reusable function for showing either a new step in the depixelization of the image or the answer."""
        pillow_image = self.screenshot.pixelated_screenshot if pixelated else self.screenshot.normal_screenshot
        byte_arr = io.BytesIO()
        pillow_image.save(byte_arr, format='PNG')
        byte_data = byte_arr.getvalue()
        qt_image = QImage.fromData(byte_data)

        # qt_image = ImageQt(self.screenshot.pixelated_screenshot) # Wasn't cooperative with temporary requests images
        pixmap = QPixmap.fromImage(qt_image)
        scaled_pixmap = pixmap.scaled(720, 480, Qt.KeepAspectRatio)
        self.label_screenshot.setPixmap(scaled_pixmap)
        self.label_screenshot.setScaledContents(True)

    def correct_answer(self):
        # Add points, show full screenshot, ask to continue and then make a new screenshot
        print("You guessed it right!")
        self.screenshot.solved = True
        new_score = int(self.label_score.text().replace('Score: ', '')) + self.screenshot.pixel_size
        self.label_score.setText(f"Score: {new_score}")
        self.label_hangman.setText(' '.join(x for x in self.screenshot.game_name))
        self.display_screenshot(pixelated=False)
        self.button_game_name.setText("Continue?")  # Prep for next time this one button is pressed

    def guess_game_name(self) -> None:
        """Primary logic that tests your guess against answer, giving you hangman/pixelation hints as you make mistakes"""
        if self.screenshot.solved:
            self.set_up_a_screenshot()
            return

        player_guess = self.entry_game_name.text().lower().strip() if self.entry_game_name.text() else '' # Empty text box means a None value
        game_name_lower = self.screenshot.game_name.lower()

        # Fully guessed it right inside the box
        if player_guess == game_name_lower:
            self.correct_answer()
            return

        current_hangman_corrected = ''.join([letter if letter else ' ' for letter in self.label_hangman.text().split(' ')])
        print("Current Corrected Hangman Before:", current_hangman_corrected)

        # After the first answer, as long as no letter were guessed, reveal the hangman board
        if self.screenshot.first_turn:
            self.label_hangman.setText(' '.join(['_' if x != ' ' else '' for x in self.screenshot.game_name]))
        self.screenshot.first_turn = False

        # If the entered string was a substring, add it to the hangman, unless it's already been found
        if player_guess and player_guess in game_name_lower and not player_guess in current_hangman_corrected.lower():
            # Get the index(es) of the substring
            occurrences = []
            start_index = 0
            while True:
                index = game_name_lower.find(player_guess, start_index)
                if index == -1:
                    break
                occurrences.append(index)
                start_index = index + 1
            print(f"'{player_guess}' is a NEW substring as indexes {occurrences}")

            # Copy in the indexes of the correctly-guess substring
            added_hangman = ""
            index = 0
            while index < len(self.screenshot.game_name):
                print(index)
                within_range = False
                for o in occurrences:
                    if o <= index <= o + len(player_guess) - 1:
                        within_range = True
                        break
                if within_range:
                    added_hangman += self.screenshot.game_name[index]
                else:
                    added_hangman += current_hangman_corrected[index]
                index += 1

        # Grab it all again to compare for 'correct answer' section
        current_hangman_corrected = ''.join([letter if letter else ' ' for letter in self.label_hangman.text().split(' ')])
        print("Current Corrected Hangman After:", current_hangman_corrected)

        #Got enough substrings to complete the hangman
        if current_hangman_corrected == self.screenshot.game_name:
            self.correct_answer()
            return
        else:
            # Decrease the blur of the pixel
            print("Nope, wrong answer, reducing pixelation")

            # TODO Add a random letter to the hangman

            self.screenshot.pixelate_image()
            self.display_screenshot(pixelated=True)



def remove_roman_numerals(name: str) -> str:
    """A precautionary function to prevent confusion with Dark Souls 3 vs Dark Souls III. Borrowed code."""
    # Match Roman numerals using a regex
    roman_numeral_pattern = r'\bM{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\b'

    def convert_match_to_int(match):
        roman_numeral = match.group(0)
        try:
            return str(roman.fromRoman(roman_numeral))
        except roman.InvalidRomanNumeralError:
            return roman_numeral  # Return the original text if it's not valid

    # Replace Roman numerals in the title
    return re.sub(roman_numeral_pattern, convert_match_to_int, name)




def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
