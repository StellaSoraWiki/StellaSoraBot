# Run StellaSoraBot in a container

Run StellaSoraBot in a container, such as [Podman](https://podman.io) or Docker. This is easier than
installing all the necessary dependencies on your host, and is the recommended path for new users. 

## Prerequisites

- [Podman](https://podman.io) 4.0+ or another compatible runtime like Docker.
- [Podman Compose](https://github.com/containers/podman-compose) or equivalent
- [Git](https://git-scm.com)
- Internet access
- Installed Windows copy of Stella Sora. This is compatible with the Steam and Windows Standalone client
- Access to SSLuaDumper
   - If you do not, please join the [Wiki Discord](https://discord.gg/SDAGxRp2mS) and ask nicely about it
- A [Miraheze](https://miraheze.org) account on [Stella Sora Wiki](https://stellasora.miraheze.org/)

Optional:

- To accelerate the [GroundingDINO](https://github.com/idea-research/groundingdino) sprite face detection pipeline, the NVIDIA Container Toolkit and a NVIDIA GPU with CUDA support. Otherwise, it runs on the CPU and is very slow. See [Optional: Enable the GPU face-detection path](#Optional:_Enable_the_GPU_face-detection_path)
- OldAssets folder: I don't remember what this does

## Quick start

1. Clone the StellaSoraBot repository

   ```bash
   git clone https://github.com/StellaSoraWiki/StellaSoraBot.git
   cd StellaSoraBot
   ```

2. Create folders that will persists across container rebuilds and bot runs

   ```bash
   mkdir -p vendor assets apicache
   ```

   - `vendor`: Dependencies that are private or cloned in at runtime
   - `assets`: Export directory for bot dumped assets, can get very large (~80GB)
   - `apicache`: Cache folder for pywikibot

3. Clone `SSLuaDumper` into the `vendor` directory

   You can do this either via `git clone` if your host has the necessary credentials:

   ```bash
   git clone https://github.com/StellaSoraWiki/SSLuaDumper.git vendor/SSLuaDumper
   ```

   Or, get a tarball from GitHub and extract it into `vendor`

4. Create the pywikibot password file named `user-passwords.py` in the repository root:

   ```python
   ('<username>', BotPassword('StellaSoraBot', 'verysecretpassworddonotshare'))
   ```

   Generate the bot password at [`Special:BotPasswords`](https://stellasora.miraheze.org/wiki/Special:BotPasswords). You must use `StellaSoraBot` as the bot password name.

   It needs the permissions:
   - I don't remember
   - I don't remember
   - I don't remember
   - WIP

5. Edit line 6 and 15 of `user-config.py` to match your wiki username.
   This is a must to avoid being blocked by Miraheze, see [https://meta.miraheze.org/wiki/Tech:User_Agents](https://meta.miraheze.org/wiki/Tech:User_Agents)

   Line 6:
   ```python
   usernames['ss']['ss'] = '<username>'
   ```

   Line 15:
   ```python
   user_agent_format = "Test bot by User:<username>"
   ```

6. Prevent Git from tracking `user-config.py`

   ```bash
   git update-index --skip-worktree user-config.py
   ```

7. Open `compose.yaml` in a text editor such as `nano`.
   Replace the placeholder path `/EDIT/ME/StellaSora_EN` under `volumes` with the game files directory containing the `StellaSora_Data` and `Persistent_Store` folders.

   ```yaml
         - /home/<username>/games/StellaSora_EN:/data/game:Z
   ```

8. Build the container image and start the service in detached mode:

   ```bash
   podman compose up -d --build
   ```

   If you use Docker, run `docker compose up -d --build`.

## Run the bot

Run commands on the bot using `podman compose exec bot <command>`. For example, to export Live2Ds:

```bash
podman compose exec bot uv run -m tools.live2d_into_zips
```

### First run

When runing the bot for the first time, it is essential to run these commands in order.

1. Unpack assets and compile raw dumps from the game directory:

   ```bash
   podman compose exec bot uv run -m unpack.unpack_main
   ```

2. Generate wiki markup and upload revised core wiki pages:

   ```bash
   podman compose exec bot uv run -m main
   ```

3. Process character galleries and upload secondary media:

   ```bash
   podman compose exec bot uv run -m main2
   ```

### On updates

TODO document how to rebuild container
Something like pull git repo,`podman ps` then find the name of the StellaSoraBot container then `podman rm` it, run `podman compose up --build` again

* Run `main2` when the game updates

  ```bash
  podman compose exec bot uv run -m main2
  ```

* Run `main` after both the game and the `StellaSoraData` repository update

  ```bash
  podman compose exec bot uv run -m main
  ```

* Run `main_other` when... 

  ```bash
  podman compose exec bot uv run -m main_other
  ```

* Run individual one-off scripts

  ```bash
  podman compose exec bot uv run -m <package>.<module>
  ```

### Dump Live2D models to ZIPs for [StellaSoraLive2Ds](https://github.com/ParasailNumerous/StellaSoraLive2Ds)

todo

### Export 3D models to [StellaSoraModels](https://github.com/StellaSoraWiki/StellaSoraModels)

Todo

## View Live2D models in the browser

> [!IMPORTANT]
> This may be removed and replaced. The reconmmended flow is to use the [l2d-viewer](https://stellasorawiki.github.io/l2d-viewer/) web app, and import exported zips found in `assets/live2d_zips` via `podman compose exec bot uv run -m tools.live2d_into_zips`

The service exposes port 8000 on the host. You can run the built-in HTTP server to inspect exported Live2D assets.

1. Start the HTTP server inside the running container:

   ```bash
   podman compose exec bot uv run python -m http.server 8000
   ```

2. Open the following URL in a web browser on the host:

   ```text
   http://localhost:8000/tools/live2d_viewer.html
   ```

3. Press `Ctrl+C` in your terminal when you want to stop the HTTP server.

## Optional: Enable the GPU face-detection path

The `main_other` entry point uses GroundingDINO and PyTorch for sprite face detection and 3D model processing. This optional pipeline requires an NVIDIA GPU and dedicated dependencies.

1. Install the NVIDIA Container Toolkit on your Linux host. Configure the container runtime to expose NVIDIA GPUs.

2. Open `Containerfile` in a text editor. Replace the line `&& uv sync --frozen` with `&& uv sync --frozen --extra grounding`:

   ```dockerfile
   uv sync --frozen --extra grounding
   ```

3. Open `compose.yaml` in a text editor such as `nano`. Uncomment the `deploy` reservation block at the bottom of the `bot` service definition:

   ```yaml
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: all
                 capabilities: [gpu]
   ```

4. Rebuild and restart the container service:

   ```bash
   podman compose up -d --build
   ```

5. Run the GPU-accelerated workflow module:

   ```bash
   podman compose exec bot uv run -m main_other
   ```
