from character_info.char_sprite_face import sprite_face_main
from page_generators.model_viewer import save_manifest
from unpack.unpack_model import export_3d_models


def main():
    # Require CUDA. Super slow otherwise.
    sprite_face_main()
    # Need access to GH repo.
    export_3d_models()
    save_manifest()


if __name__ == "__main__":
    main()
