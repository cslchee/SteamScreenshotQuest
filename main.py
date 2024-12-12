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
        elif not steam_id and DEFAULT_STEAM_ID is not None: # Set default the steam key from .env
            steam_id = DEFAULT_STEAM_ID
        if len(steam_id) != 17 or not steam_id.isalnum():
            raise ValueError(f"You've entered an invalid Steam ID.\nCheck the length and make sure it's numeric.")
        steam_id = steam_id.upper()

        self.steam_id = steam_id
        self.points = 0
        self.player_name = self.get_player_name()
        self.steam_games_ids = self.get_player_steam_games()
        print("PANG")

    def get_player_name(self) -> str:
        player_info_url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={self.steam_id}&format=json"
        soup = BeautifulSoup(requests.get(player_info_url).text, "html.parser")
        try:
            data = json.loads(soup.text)
        except Exception:
            raise ValueError("Could not talk to the Steam API. Is your key valid/correct?")
        if not data['response']['players']:
            raise ValueError("Error with retrieving Steam Profile. Likely an invalid ID.")
        return data['response']['players'][0]['personaname']


    def get_player_steam_games(self) -> list[int]:
        """Given a valid Steam ID, get all the games that the player has"""
        if STEAM_API_KEY is None:
            raise ValueError("No Steam API Key provided in the .env file.")
        player_games_url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={self.steam_id}&format=json"
        print(player_games_url)
        soup = BeautifulSoup(requests.get(player_games_url).text, "html.parser")
        data = json.loads(soup.text)
        if data['response'] == {}:
            raise ValueError("This profile is private and their Steam games cannot be viewed.")
            # Hypothesis - You can still access the friends-only private profiles of accounts tied to you and therefore your API key
        try:
            data_games = data['response']['games']
        except KeyError:
            raise ValueError(f"You've entered an invalid Steam ID. Player ID does not exist.") # Already tested for valid API in get_player_name

        data_ids = [game['appid'] for game in data_games if game['playtime_forever'] > 15] # Grab game ideas, ignore unplayed games
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
        self.starting_pixel_size = 50 # Used for percentage of final round score. Constant.
        self.pixel_size_decrease = 10 # Also used for percentage of final score. Constant.
        self.pixel_size = self.starting_pixel_size # The pixelation value that changes while the game is playing.
        self.turn_counter = 0 #Required for hinting hangman
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
            for grammar in '®™©,.:;?\'"-()[]{}!<>':
                name = name.replace(grammar, '')
            name = remove_roman_numerals(name)
            name = name.title()
            name = name.replace('&', 'and')
            for edition in ('Game Of The Year Edition','Definitive Edition','Complete Edition', 'Ultimate Edition'):
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
        if self.turn_counter != 0: # Don't initially remove pixel size on the first turn
            self.pixel_size -= self.pixel_size_decrease
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
        self.entry_game_name.setStyleSheet("font-size: 20px; font-family: Arial; font-style: italic;")
        self.entry_game_name.setText("Enter Game Name Here... (Get a Hint with 'Submit')")

        self.button_game_name.clicked.connect(self.guess_game_name)
        self.button_game_name.setDisabled(True)

        # Apply generic, repeated traits. Like using a class in CSS
        for x in (label_enter_id, self.label_id_warning_and_welcome, label_question, self.label_score, self.label_hangman):
            x.setAlignment(Qt.AlignCenter)
        for x in (self.entry_steam_id, self.button_submit_id, label_question, self.label_hangman, self.button_game_name,
                  self.label_id_warning_and_welcome):
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
        self.entry_game_name.setText("")

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

    def round_ended(self, won=True):
        """Add points, show full screenshot, ask to continue and then make a new screenshot"""
        print("This round is complete!")
        self.screenshot.solved = True
        # Give points based on the remaining pixel size of the screenshot. A pixel size of '1' (normal resolution) means 0 points
        calculated_score = int(100 * (self.screenshot.pixel_size / self.screenshot.starting_pixel_size)) if won else 0 # A percentage of 50 points based on the
        new_score = int(self.label_score.text().replace('Score: ', '')) + calculated_score
        self.label_score.setText(f"Score: {new_score}")
        self.label_hangman.setText(' '.join(x for x in self.screenshot.game_name))
        self.display_screenshot(pixelated=False)
        self.button_game_name.setText("Continue?")  # Prep for next time this one button is pressed, don't call set_up_a_screenshot yet

    def guess_game_name(self) -> None:
        """Primary logic that tests your guess against answer, giving you hangman/pixelation hints as you make mistakes"""
        if self.screenshot.solved:
            self.set_up_a_screenshot()
            return

        player_guess = self.entry_game_name.text().lower().strip() if self.entry_game_name.text() else '' # Empty text box means a None value
        game_name_lower = self.screenshot.game_name.lower()

        current_hangman_corrected = ''.join([letter if letter else ' ' for letter in self.label_hangman.text().split(' ')])
        #print(f'Current Hangman Corrected: "{current_hangman_corrected}"')

        """
            Win condition:
                Fully guessed it right inside the box
            Continue condition:
                OR ran out of characters to add to the hangman
                OR run out have the image completely depixelate 
        """
        if player_guess == game_name_lower:
            self.round_ended(won=True)
            return
        elif current_hangman_corrected == self.screenshot.game_name or self.screenshot.pixel_size == 1:
            self.round_ended(won=False)
            return

        # After the first answer, as long as no letter were guessed, reveal the hangman board
        if self.screenshot.turn_counter == 0:
            self.label_hangman.setText(' '.join(['_' if x != ' ' else '' for x in self.screenshot.game_name]))

        #Wrong answer/hint needed, reducing pixelation, show a new letter if the hangman board is up (after first mistake)
        if self.screenshot.turn_counter > 0:
            def add_letters_to_hangman(new_letters: list[str]) -> str:
                """Add all instances of a letter(s) (upper and lower) to the hangman"""
                the_hangman = ""
                for index in range(len(game_name_lower)):
                    if game_name_lower[index] in new_letters:
                        the_hangman += self.screenshot.game_name[index]  # Accommodates upper/lower cases
                    else:
                        the_hangman += current_hangman_corrected[index]  # Get the other letters and underscores
                print("New hangman: ", the_hangman)
                return the_hangman

            # On the turn after the empty hangman is revealed, display the first letters of each word
            if self.screenshot.turn_counter == 1:
                first_letters = [x[0] for x in game_name_lower.split(" ")]
                print("Showing first letters: ", first_letters)
                new_hangman = add_letters_to_hangman(first_letters)
            else:
                # On every turn after the first letters of each work are revealed, add a stray letter or two
                vowels_and_consonants = ('aeiou','aeiou','bcdfghjklmnpqrstvwxyz') # 66% chance to get a vowel/consonant
                letter_set = []

                def pick_an_unused_letter() -> str:
                    pick_a_letter = random.choice(random.choice(vowels_and_consonants))
                    print(f"Picking the letter... {pick_a_letter}", end='')

                    # Keep picking a letter until you get a new one that's in the game_name but not the current known letters
                    loop_protection = 0 # In case there's trouble randomly narrowing down that last letter
                    while pick_a_letter in current_hangman_corrected.lower() or pick_a_letter not in game_name_lower or pick_a_letter in letter_set:
                        pick_a_letter = random.choice(random.choice(vowels_and_consonants))
                        print(f" -> {pick_a_letter}", end='')
                        if loop_protection > 26:
                            print('Break', end='')
                            break
                        loop_protection += 1
                    print()
                    return pick_a_letter

                # Add more than one letter if the number of _'s in the current hangman is higher
                for x in range(2 if current_hangman_corrected.count("_") > 6 else 1):
                    letter_set.append(pick_an_unused_letter())

                new_hangman = add_letters_to_hangman(letter_set)


            self.label_hangman.setText(' '.join([x if x != ' ' else '' for x in new_hangman]))

        self.screenshot.turn_counter += 1

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
