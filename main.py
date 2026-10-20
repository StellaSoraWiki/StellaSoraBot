import subprocess
from pathlib import Path

from character_info.audio import generate_audio_page
from character_info.char_affinity import affinity_main
from character_info.char_images import upload_char_images
from character_info.char_infobox import update_infobox
from character_info.char_potential import potential_main
from character_info.char_profile import update_character_profile
from character_info.char_skills import skill_main
from character_info.char_stats import update_character_stats
from character_info.char_story import update_character_stories
from character_info.private_message import update_private_messages
from page_generators.discs import update_disc_all
from page_generators.events import save_event_all
from page_generators.live2d_talent_images import live2d_talent_images_main
from page_generators.purge_pages import purge_all_pages
from story import (
    export_char_story,
    export_disc_story,
    export_event_story,
    export_main_story,
    export_nova_times,
)
from utils.data_utils import autoload_all_files


def update_character_page():
    upload_char_images()
    live2d_talent_images_main()
    update_infobox()
    skill_main()
    update_character_stats()
    affinity_main()
    potential_main()
    update_character_stories()
    update_private_messages()
    generate_audio_page()
    update_character_profile()


def export_all_stories():
    export_main_story.main()
    export_event_story.main()
    export_char_story.main()
    export_disc_story.main()
    export_nova_times.main()


def main():
    subprocess.run(["git", "pull"], check=True, cwd=Path("./vendor/StellaSoraData"))
    autoload_all_files()
    update_character_page()
    save_event_all()
    update_disc_all()
    export_all_stories()
    purge_all_pages()


if __name__ == "__main__":
    main()
