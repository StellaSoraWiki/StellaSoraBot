import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pywikibot import Page
from wikitextparser import parse, Template

from character_info.characters import get_characters, get_character_pages, get_id_to_char, Character
from page_generators.archive_notes import update_archive_notes
from utils.data_utils import autoload, assets_root
from utils.text_utils import escape_text
from utils.upload_utils import UploadRequest, process_uploads
from utils.wiki_utils import force_section_text, save_page, set_arg


@dataclass
class AffinityArchive:
    id: int
    title: str
    content: str
    updated_content: str | None = None


@cache
def get_affinity_archives() -> dict[str, list[AffinityArchive]]:

    def add_archive_file(c: str) -> str:
        filename = ""
        if "acrchives_certified" in c:
            filename = "certified"
        if "acrchives_falsified" in c:
            filename = "falsified"
        if filename != "":
            repl = f"[[File:Archive {filename}.png|30px|link=]]"
            c = re.sub("<sprite[^>]+>", repl, c)
        return c

    chars = get_characters()
    result = {}
    data = autoload("CharacterArchiveContent")
    for name, char in chars.items():
        lst = []
        for i in range(2, 14):
            key = f"{char.id}{i:02}"
            if key not in data:
                break
            row = data[key]
            content = row['Content']
            content = escape_text(content)
            content = add_archive_file(content)
            updated_content = row['UpdateContent1']
            if key in updated_content:
                updated_content = None
            else:
                updated_content = escape_text(updated_content)
                updated_content = add_archive_file(updated_content)
            lst.append(AffinityArchive(
                id=row['Id'],
                title=row['Title'],
                content=content,
                updated_content=updated_content,
            ))
        else:
            result[name] = lst
    return result


@dataclass
class InvitationStory:
    id: int
    name: str
    clue: str
    landmark: str
    option: str
    memory: str
    desc: str

    @property
    def file_page(self) -> str:
        return f"Date CG {self.id}.png"

    @property
    def file_path(self) -> Path:
        return assets_root / "icon" / "datingeventcg" / f"datingspcg_{self.id}.png"


@cache
def get_landmark_names() -> dict[int, str]:
    return {v['Id']: v['Name'].removeprefix("The ") for v in autoload("DatingLandmark").values()}


@cache
def get_landmark_branches() -> dict[int, dict]:
    return {v['DatingEventParams'][0]: v for v in autoload("DatingBranch").values() if v['DatingEventType'] == 7}


def get_landmark_option(landmark_id: int, branch: int) -> str:
    branches = get_landmark_branches()
    assert landmark_id in branches, f"Landmark {landmark_id} has no branch options"
    return branches[landmark_id][f"Option{branch}"]


def get_invitation_stories() -> dict[str, list[InvitationStory]]:
    chars = get_id_to_char()
    data = autoload("DatingCharacterEvent")
    result: dict[str, list[InvitationStory]] = {}
    for k, v in data.items():
        event_id = v['Id']
        char_id = event_id // 1000
        if char_id not in chars:
            continue
        char = chars[char_id]
        desc = "\n\n".join(v[f"Desc{i}"] for i in range(1, 10) if f"Desc{i}" in v)
        landmark_id = v['DatingEventParams'][1]
        result[char.name] = result.get(char.name, [])
        result[char.name].append(InvitationStory(
            id=event_id,
            name=v['Name'],
            clue=v['Clue'],
            landmark=get_landmark_names()[landmark_id],
            option=get_landmark_option(landmark_id, v['BranchTag']),
            memory=v['Memory'],
            desc=desc,
        ))
    return result


def affinity_archive_sections(stories: list[AffinityArchive]) -> str:
    result = []
    for story in stories:
        result.append("{{Collapse|1=" + story.title + "|2=" + story.content + "}}")
        if story.updated_content:
            result.append("{{Collapse|1=" + story.title + " (updated)|2=" + story.updated_content + "}}")
    return "\n\n".join(result) + "\n"


def upload_invitation_story_images() -> None:
    stories = get_invitation_stories()
    upload_requests = []
    for story_list in stories.values():
        for story in story_list:
            upload_requests.append(UploadRequest(
                story.file_path,
                story.file_page,
                '[[Category:Invitation story images]]',
                'batch upload invitation story images',
            ))
    process_uploads(upload_requests)


def invitation_story_sections(stories: list[InvitationStory]) -> str:
    result = ["{{InvitationStorySection}}"]
    for story in stories:
        result.append(f"==={story.name}===")
        template = Template("{{InvitationStory\n}}")
        set_arg(template, "title", story.name)
        set_arg(template, "file", story.file_page)
        set_arg(template, "clue", story.clue)
        set_arg(template, "landmark", story.landmark)
        set_arg(template, "option", story.option)
        set_arg(template, "memory", story.memory)
        set_arg(template, "desc", story.desc)
        result.append(str(template))
    return "\n".join(result)


def save_story_page_content():
    affinity_archives = get_affinity_archives()
    invitation_stories = get_invitation_stories()
    for char, page in get_story_pages().items():
        if page.exists():
            parsed = parse(page.text)
        else:
            parsed = parse("""{{StoryTop}}
==Affinity archives==
==Heartlink chat==
==Anecdotes==
==Invitation stories==
""")
        text = affinity_archive_sections(affinity_archives[char.name])
        force_section_text(parsed, "Affinity archives", text)
        text = invitation_story_sections(invitation_stories[char.name])
        force_section_text(parsed, "Invitation stories", text)
        save_page(page, str(parsed), "update character story")


def get_story_pages() -> dict[Character, Page]:
    return get_character_pages(suffix="/story", must_exist=False)


def update_character_stories():
    upload_invitation_story_images()
    save_story_page_content()
    update_archive_notes()


def main():
    update_character_stories()


if __name__ == '__main__':
    main()
