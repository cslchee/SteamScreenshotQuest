import requests, json, random
from PIL import Image
from dotenv import load_dotenv
from os import getenv
from bs4 import BeautifulSoup
from io import BytesIO

load_dotenv()
DEFAULT_STEAM_ID = getenv("DEFAULT_STEAM_ID")
STEAM_API_KEY = getenv("STEAM_API_KEY")

class Player:
    def __init__(self, steam_id: str):
        if steam_id is None:
            raise ValueError("You've entered an invalid Steam ID. No default value specified in .env file.")
        if len(steam_id) != 17 or not steam_id.isalnum():
            raise ValueError(f"You've entered an invalid Steam ID. Invalid format.")
        steam_id = steam_id.upper()
        self.steam_id = steam_id
        self.points = 0
        self.steam_games_ids = self.get_player_steam_games()

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

def get_random_game_screenshot(game_id: int) -> tuple[str, Image]:
    """Go the game's Steam page, grab it's title, check its tags, grab a random screenshots and put it in a pillow Image"""
    game_url = f"https://store.steampowered.com/app/{game_id}/"
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
    screenshots = [image['src'] for image in soup.select('img') if f'store_item_assets/steam/apps/{game_id}/' in image['src'] and '116x65.' in image['src']]
    random_high_res_link = random.choice(screenshots).replace('116x65','1920x1080')
    random_high_res_link = random_high_res_link[:random_high_res_link.index("?")] #Remove trailing '?t='
    random_screenshot = Image.open(BytesIO(requests.get(random_high_res_link).content)).convert('RGB')

    return name, random_screenshot

def pixelate_image(image: Image, pixel_size: int) -> Image:
    """Downsides and the upsizes an Image"""
    small_image = image.resize((image.width // pixel_size, image.height // pixel_size), Image.BILINEAR)
    pixelated_image = small_image.resize(image.size, Image.NEAREST)
    return pixelated_image


# Ask for Steam ID/Username and create player from ID
player_steam_id = input("Please enter ur Steam ID >_")
player = Player(player_steam_id if player_steam_id else DEFAULT_STEAM_ID)
# #TODO Catch ValueErrors, print 'e', and reprompt user

# Get a screenshot from game's Steam store page
random_game_name, random_screenshot = get_random_game_screenshot(player.random_game_id())

# Create pixelated version
pixelated_image = pixelate_image(random_screenshot, 25)
pixelated_image.show()
