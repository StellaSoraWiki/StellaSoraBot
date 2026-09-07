#!/usr/bin/env bash
set -euo pipefail

# script initalizes Debian enviornment to use StellaSoraBot

# Can't run as root user otherwise things break badly so fail fast when detecting it
# stolen from https://unix.stackexchange.com/a/20325
if [[ $EUID -eq 0 ]]; then
  echo "This script must NOT be run as root. If using WSL, setup a user account and login to it." 1>&2
  exit 1
fi

cd $HOME

sudo apt-get update
sudo apt-get upgrade
# uses of each package
# curl: install uv (https://docs.astral.sh/uv/)
# git: clone repos
# build-essential: build C++ Python wheels
# wget: download deps and executables
# ffmpeg: used in bot for wav_to_ogg among other things
# default-jre: for decrypting lua files in a vendor dependency
sudo apt-get install -y curl git build-essential wget ffmpeg default-jre

# adapted from https://learn.microsoft.com/en-us/dotnet/core/install/linux-debian
# adds the Microsoft package signing key to list of trusted keys and adds the package repository
wget https://packages.microsoft.com/config/debian/13/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
rm packages-microsoft-prod.deb

# update again after adding Microsoft package repo
sudo apt-get update && \
  sudo apt-get install -y dotnet-sdk-8.0

# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# download vgmstream-cli binary and move it to user bin file
wget https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-linux-cli.tar.gz -O packages-vgmstream-cli-nightly.tar.gz
tar -xzf packages-vgmstream-cli-nightly.tar.gz
mv vgmstream-cli ~/.local/bin
rm packages-vgmstream-cli-nightly.tar.gz

# updates PATH so uv works without restarting shell
source $HOME/.local/bin/env

# adapted from https://github.com/lihaohong6/StellaSoraBot/blob/master/README.md
git clone https://github.com/lihaohong6/StellaSoraBot.git
cd StellaSoraBot
# C++ wheels break on latest version of Python (3.14) due to changes
uv python pin 3.13
uv sync
# Playwright is used for rendering L2d's
uv run playwright install chromium

# bot setup done! now install stella sora

# Commented out because WSL2 Bottles isn't being used anymore, stop here
exit 0

# Navigate up back to home directory
cd $HOME

# Install Flatpak and Bottles, then creates a empty Bottle to run Stella Sora in

sudo apt-get install flatpak -y
sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
sudo flatpak install flathub com.usebottles.bottles

# reference: https://docs.usebottles.com/advanced/cli
# This was "StellaSora" before but the upstream repo name defaults to "Stella Sora" so changed it to that
flatpak run --command=bottles-cli com.usebottles.bottles new \
  --bottle-name "Stella Sora" \
  --environment "gaming" \
  --arch "win64"

# Download the Yostar StellaSora game launcher and move it to the bottle directory
# (this is done because otherwise it works weirdly with the flatpak sandboxing)

# pulled from https://lutris.net/games/install/39750/view, not sure if it's still right
wget https://launcher-pkg-ss-en.yo-star.com/install_pkg/game_launcher/StellaSora_EN/StellaSora_EN_Gamelauncher-1.6.0-setup.exe -O StellaSora_EN_Launcher.exe
mv StellaSora_EN_Launcher.exe ~/.var/app/com.usebottles.bottles/data/bottles/bottles/Stella-Sora

wget https://aka.ms/vc14/vc_redist.x86.exe -O vc_redist.x86.exe
mv vc_redist.x86.exe ~/.var/app/com.usebottles.bottles/data/bottles/bottles/Stella-Sora

# user needs to interactively install game, script is done
# echo "You need to install the game. If you already know how to install it in Bottles, ignore these instructions."
# echo "First, start Bottles using the command flatpak run com.usebottles.bottles"
# echo "Bottles will already be setup. Navigate to the Bottles tab, then select the \"Stella Sora\" bottle."
# echo ""
# echo "Install dependencies for Stella Sora launcher:"
# echo "  Navigate to Dependencies, and search for \"vcredist2019\ and \"webview2\", and install them both."
# echo "If you would like to install Proton-GE:""
# echo "  On the home page, navigate to Main Menu > Preferences > Runners > proton-GE and install the latest version."
# echo "  Then, back on the bottle page, set Settings > Runner to \`ge-proton*\`."
# echo ""
# echo "When you are done, the launcher is located at StellaSora_EN_Launcher.exe in the same directory as the bottle."
# echo "Run the executable and finish the install process."

# echo "After installing the game, you must start it, then choose a voice language to download, but you don't have to do the prologue"
# echo "Continue instructions from https://github.com/lihaohong6/StellaSoraBot/blob/master/README.md"

printf "%s\n" \
"" \
"" \
"" \
"You need to install the game. If you already know how to install it in Bottles, ignore these instructions." \
"First, start Bottles using the command flatpak run com.usebottles.bottles" \
"Bottles will already be setup. Navigate to the Bottles tab, then select the \"Stella Sora\" bottle." \
"" \
"Install dependencies for Stella Sora launcher:" \
"- Navigate to Dependencies, and search for \"vcredist2019\" and \"webview2\", and install them both." \
"If you would like to install Proton-GE:" \
"- On the home page, navigate to Main Menu > Preferences > Runners > proton-GE and install the latest version." \
"- Then, back on the bottle page, set Settings > Runner to \`ge-proton*\`." \
"Under Settings > Display Settings," \
"Enable Virutal Desktop." \
"Install Visual C++ Redistributable under vc_redist.x86.exe" \
"" \
"When you are done, the launcher is located at StellaSora_EN_Launcher.exe in the same directory as the bottle." \
"Run the executable and finish the install process." \
"" \
"After installing the game, you must start the game, progress past the point where you choose a voice language to download, and you can stop at the login page." \
"Continue instructions from https://github.com/lihaohong6/StellaSoraBot/blob/master/README.md" \
"" \
"" \
"" 

# install CUDA
# wget https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/cuda-keyring_1.1-1_all.deb
# sudo dpkg -i cuda-keyring_1.1-1_all.deb


# wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
# sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
# wget https://developer.download.nvidia.com/compute/cuda/13.3.1/local_installers/cuda-repo-wsl-ubuntu-13-3-local_13.3.1-1_amd64.deb
# sudo dpkg -i cuda-repo-wsl-ubuntu-13-3-local_13.3.1-1_amd64.deb
# sudo cp /var/cuda-repo-wsl-ubuntu-13-3-local/cuda-*-keyring.gpg /usr/share/keyrings/
# sudo apt-get update
# sudo apt-get -y install cuda-toolkit-13-3

# wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
# sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
# wget https://developer.download.nvidia.com/compute/cuda/12.8/local_installers/cuda-repo-wsl-ubuntu-12-8-local_12.8-1_amd64.deb
# sudo dpkg -i cuda-repo-wsl-ubuntu-12-8-local_12.8.1-1_amd64.deb
# sudo cp /var/cuda-repo-wsl-ubuntu-12-8-local/cuda-*-keyring.gpg /usr/share/keyrings/
# sudo apt-get update
# sudo apt-get -y install cuda-toolkit-13-3