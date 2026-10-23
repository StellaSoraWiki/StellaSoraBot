# 3D model exports and local viewer

Exports Stella Sora character models to glTF and previews local files with the
wiki’s ModelViewer gadget loaded from jsDelivr.

## Use

```bash
uv run -m unpack.unpack_model                             # every character and clip
uv run -m unpack.unpack_model --char-id 13301             # one character
uv run -m unpack.unpack_model --char-id 13301 --no-animations
uv run -m unpack.unpack_model --jobs 4                    # fewer characters at once

python3 -m http.server 8777          # then open :8777/tools/model_viewer.html
```

Open <http://localhost:8777/tools/model_viewer.html> after starting the server
from the repository root. Models, animation manifests and clips come from
`assets/assetbundles/actor3d/` on your machine. The page loads exactly:

```text
https://cdn.jsdelivr.net/gh/lihaohong6/MirahezeDevScripts@dist/dist/ModelViewer/gadget-impl.js
```

The bundle supplies the rendering code, controls and CSS. A small local
MediaWiki adapter runs its ResourceLoader wrapper and page hooks; controls use
native browser styling in place of the wiki’s Codex stylesheet. three.js is
loaded by the gadget, so an internet connection is required.

Pick any exported base model or variant in the gadget’s **Model** dropdown,
then choose its animation. Variants include all of their base model’s clips
alongside their own; when both libraries contain the same name, the variant’s
copy is labelled `(variant)`. Other characters’ clips are excluded. Per-clip
`show`/`hide` rules are preserved. Playback, scrubbing and speed controls come
from the gadget.

Reload after re-exporting. Each page load adds a fresh query parameter to
local asset URLs and bypasses the JSON cache, so unpublished changes can be
checked without pushing the model repository or refreshing jsDelivr.

Characters already exported are skipped; pass `--overwrite` to redo them. The
first run builds `assets/assetbundles/cab_index.json` (~1 min, 9,640 bundles);
it is cached. A library without exported clips opens in the bind pose.

Characters export in parallel, one process each. All 50 with their clips takes
about 70 seconds on 20 cores. A character peaks near 2 GB and UnityPy hands
little of it back, so `--jobs` is worth lowering on a machine with less memory
than cores would suggest; it defaults to cores minus four.

The viewer defaults to unlit shading and a 25% outline. Rendering and animation
behavior are provided by the published gadget.

## How it works

`unpack/unpack_model.py` reads the `char_<id>{,_models,_materials,_textures}` bundles and
writes one `.glb` per character, holding:

- meshes with normals, UVs, vertex colours, skin weights and bind poses
- the `Root/Bip001` skeleton as a glTF skin
- `_SMOOTHNORMAL`, the outline-extrusion normal that Toony Colors Pro bakes into
  the mesh tangent (its `w` is 0, which is how you tell it from a real tangent)
- all five toon maps, and every toon float/colour, in material `extras`

Standard PBR fields are filled in too, so the files open in any glTF viewer —
they just look flat there. LOD meshes are skipped unless `include_lod=True`.

`CustomModelLODGroup` on the prefab root lists the renderers the game shows when
a model spawns. Everything outside that list — cutscene props, alternate
weapons, emote quads — waits for a script to enable it, so the exporter marks
those meshes `extras.optional` and the viewer starts them hidden. Some of them
ship with the GameObject already inactive and some do not, which is why the
group is the signal rather than `m_IsActive`.

Cross-bundle references are resolved through `cab_index.json`. Without it the
face lightmap and the shared matcap silently fail to load, because they live
outside the per-character bundles.

Every character gets its own subdirectory, named after the character rather
than its numeric id — `Amber/`, not `char_10301/` — and everything the
exporter writes for it lands there rather than loose in the output root, which
stays a bare `index.json` plus one subdirectory per character. The `.glb`
inside takes that same name (`Amber/Amber.glb`); an alternate skin appends its
own title, in the `Character: Skin` style `CharacterSkin.Name` already uses
for the default skin (`Amber: Ease Into an Unhurried Summer`), slugged for the
filesystem and the URL the viewer fetches it from
(`Amber/Amber_Ease_Into_an_Unhurried_Summer.glb`) — still inside the
character's own subdirectory, alongside the default skin. `index.json` keeps
both forms: the slugged path as `file`, the pretty form as `label`.

## Animations

It also reads `char_<id>_animations.unity3d` and `char_<id>_timeline.unity3d`,
and writes one `.glb` per clip into a flat `<name>_anims/` directory next to
the model, plus a `<name>.anims.json` manifest — `Amber/Amber_anims/Ready.glb`
and `Amber/Amber.anims.json` — where `<name>` is the same slugged
character/skin name as the model. A clip's own name usually repeats the
character's id (`133_Ready`), or — for an alt outfit's own timeline cutscene —
the 5-digit skin id instead (`13303_Ready`); since clips are already grouped
one character at a time, that token is redundant and the exporter drops it, so
the clip above is named and filed simply `Ready`. The viewer loads each clip on
demand and retargets it onto the model by bone name. Alternate outfits fall back
to the default outfit's bundle for each missing animations or timeline bundle.

Transform tracks under `Root/Bip001` are retained even when the exporting
outfit's prefab has no matching bone. Shared clips include bones used only by
other outfits: Amber's swimsuit, for example, weights its limbs to six twist
bones absent from her default model. Filtering against that default prefab
removed their animation and deformed the swimsuit's arms and legs. Tracks that
hold the exporting model's rest pose are retained too, since another outfit
can have a different rest transform. Viewers ignore tracks for absent bones.
Re-export existing clips to apply this fix; the model files need no changes.

The clips are generic (non-humanoid) Mecanim, so there is no muscle rig to
decode — just float curves. `m_MuscleClip.m_Clip` splits them across three
storage classes sharing one index space: `m_StreamedClip` (sparse, cubic),
`m_DenseClip` (uniform samples) and `m_ConstantClip`. `m_ClipBindingConstant`
carves that index space back into per-transform position (3 curves), rotation
(4) and scale (3), and `Avatar.m_TOS` turns each binding's CRC path hash into a
bone path.

A streamed key stores the coefficients of the cubic running to the next key, so
sampling it is exact. The exporter evaluates every curve onto the union of its
keys and the authoring frame grid, bisects any interval where a straight line
still misses the curve by more than half a degree, then drops every key the
line does reproduce — most of them, since bones are keyed on every frame. Worst
case over a clip lands near 1°; without the bisection a fast weapon spin was 19°
out mid-frame. With normalised-int16 quaternions the median clip is 100 KB.

Note the first and last streamed frames are sentinels holding pre- and post-wrap
state — and the first is stamped `-FLT_MAX`, not `-inf`, so it survives an
`isfinite` check.

Sampling before a curve's first key holds that key, as Unity's clamped wrap does,
rather than running the cubic backwards from it. Every transform curve is keyed
from the clip start, so this never came up until blend shapes did: a shape keyed
only over the moment it fires starts seconds in, and extrapolating backwards to
`t=0` put char_13403's `face01` at -4088%.

Transform and blend shape bindings are taken. What that leaves out:

- **Runtime-only bones** have tracks, but will only move geometry if the loaded
  model contains those bones. The viewer does not spawn bones or simulate cloth.
- **Root motion** rides on the Animator binding (`kBindMotionT`/`Q`, seven
  curves) rather than a transform track, on the dashes and lunges. Skipping it is
  deliberate: clips then play in place instead of walking out of frame.

## Expressions

A face carries one blend shape per expression — 5 to 19 of them, named `face00`
onwards, in the mesh's `m_Shapes` — and the exporter writes them out as glTF
morph targets. The deltas are sparse in Unity, runs of (vertex index, offset)
shared by every shape in the mesh, and dense in glTF, one array per target.

A clip drives them through a `SkinnedMeshRenderer` binding whose attribute is the
CRC32 of the shape name — which is exactly the hash the mesh already stores
against the channel, so nothing has to be guessed. Weights are percentages there
and unit fractions in glTF.

They are also clamped to 0–100 on the way. Where a shape sits idle the bundle
keys it only every ~0.8 s, and the cubic joining those sparse keys wanders far
outside anything a weight can mean: 133_Ready holds `face01` at 100 for 1.4 s but
swings to 578 in between, against `face02` at -483. Every blend shape channel in
every model tops out at a `fullWeight` of 100, so the runtime has to be clamping
too; clamp and the curve reads as authored, a hold and then a two-frame
crossfade. Excursions inside a densely keyed stretch overshoot by 1–2% at most,
so this costs nothing where the artist actually keyed something.

Only a handful of clips animate a face — Ready, ReadyLoop, Victory, VictoryLoop,
the ultra Timeline, and the occasional Die — and the manifest flags them with
`face: true`. Everything else leaves the face
neutral, including Idle and the whole combat set, so a character only changes
expression on those clips. That is what the bundles hold, not something the
exporter drops: no attack or skill clip carries a blend shape binding.

The Timeline clip is the one that emotes most, and for most characters it is not
in the animations bundle at all — it ships in `char_<id>_timeline.unity3d`
alongside its own cutscene rig. That bundle is read as a second clip source, with
its own `m_TOS`: merging the two path tables would let one rig's hashes resolve
against the other's bones. Its camera and prop clips animate nothing the model
has, produce no channels, and drop out on their own.

Roughly half of those cutscene rigs carry a reduced face — 4 shapes where the
model has 13, say. Because a binding is matched on the CRC32 of the shape *name*
rather than a channel index, the shapes it does have still land on the right
morph target, and the ones it lacks find no match and are left out. This assumes
`face03` means the same expression on both rigs, which is the same assumption the
animations bundle already relies on.

char_10801 and char_12001 have no blend shapes on the face mesh at all, so they
stay neutral everywhere. Whatever the game does for their expressions, it is not
morph targets.

Each clip that has one carries a stand-in mesh — a degenerate triangle — with
the right number of shapes: a weights channel may only target a node that has morph targets, and
three.js builds no track for one that has none. The node takes the name of the
mesh in the model, and the viewer retargets the track by that name — once per
material the face is split across, since each is its own object with its own
copy of the influences.

Characters exported before this went in carry no morph targets, and their
manifests flag no clip `face`; re-export them with `--overwrite` and their faces
come to life. A viewer holding an old model drops the weights track rather than
misbinding it, so the mix is harmless — which also means a stale export fails
silently, looking exactly like a character that simply never emotes.

The *Swap-in parts* checkbox is a different thing. It reveals the meshes the
game keeps off until a script turns them on: char_10301's phone, cat and
glasses, char_14401's quilt and cup, and the emote quads (`face11_sp01`,
`face_05sp`) that a few faces use in place of a blend shape. 29 of the 50
characters carry some, and the box is greyed out for the rest. They hang off
sockets no clip animates, so left visible they drift away from the body the
moment one plays — hence hidden by default.

### Per-clip part visibility

Which clips bring those parts out is stated by the game's context rigs: the
timeline and fx bundles each ship whole copies of the model prefab — one per
context clips play in (`<id>_Ready`, `<id>_Victory`, `fx_<id>_timeline_Ultra`,
a cutscene `<id>_Actor`) — with every copy's swap-in parts already active or
inactive for that context. `rig_show_rules()` reads them, matches each copy to
the clip it names (the id and the `fx`/`base`/`timeline` furniture aside, with
a `timeline` rig also answering to `<name>_TL`), and writes the parts left on
into that clip's `.anims.json` entry as a `show` list. A copy is recognized by
mesh identity — its renderers point at the same mesh objects the model prefab
uses — and only whole copies count, since an FX prefab borrowing a single face
mesh is previewing an effect, not stating visibility.

This is a show-only overlay on the `optional` baseline: a clip with no matched
rig keeps every swap-in hidden, and a part no rig switches off never gets a
rule. Amber's rules come out exactly as the hand-written example on the
gadget's advanced docs page — the cat in `Victory` and `Timeline`, nowhere
else.

Some swap-in parts are never switched off at all. The game leaves them active
with their bones scaled to a ten-thousandth, and a clip grows them when it
wants them seen. Firstlight Noya has no context rig, so no rule showed her
`face09_sp` eye quads, and the end of her `Victory` lost its eyes: the `face09`
blend shape folds the eyes away to make room for quads that never appeared.
`PosedModel.revealed()` catches these. It measures each optional part's skinning
scale, from the determinant and not the bounding box, since two collapsed eye
quads still span the face. A part under 0.1 in the rest pose is one of these.
Any clip that takes it to 0.1 or more, sampled ten times a second, adds it to
`show`. The rule agrees with every rig-backed case, and it fills gaps the rigs
leave, `VictoryLoop` most often, which no rig names.

### Parts a clip parks off screen

A rig states the pose a clip starts from, not what the clip goes on to do, so
it keeps naming a prop the clip has since put away. The game puts one away
without deactivating the node it hangs from: it either scales that node to
nothing — Chitose's cup, quilt and sitting legs collapse to a point for every
clip she is not on her futon — or drives it out of the scene, as Ann's `Ready`
does with her dog and her weapon, about 7 m under the floor. Nothing in the
bundles says which, so `PosedModel` measures it: it re-poses the exported model
on the CPU (joint world matrices from the clip's own tracks, inverse bind
matrices, weights, 200 vertices a mesh, five times across the clip) and takes
each mesh's bounding box at each sample. What it finds off goes in that clip's
`hide` list in `.anims.json`.

A mesh is off if it measures under a hundredth of a body height at every one
of the five samples, or if its bounds never come near the body's — a body
height away in any direction, or half that when it hangs entirely below the
body, which is where a stowed prop nearly always goes. The scaled-away kind is
never quite a point (Minova's `Walk` leaves her second weapon a millimetre
across), but nothing meant to be seen is under a centimetre either, so the two
are two orders of magnitude apart. The distance arm earns its keep as well:
Otoha's `Victory` sword lies 1.9 m under the floor, a hair inside one body
height, and Shimiao's `Ultra_Run` parks her weapon out to the side rather than
below. Held props clear the body by well under half a body height even at arm's
length, and stay beside it rather than under it; a prop that only appears
midway through a clip has size at the later samples, so the first test leaves
it alone. The body is taken as the mesh with the most vertices rather than by
name, since a few models call it `cloth`. Names in both lists are dropped from
`show`, because the viewer applies `hide` first and `show` second. 39 of the 52
models have something to hide, 512 clips between them.

What no rig states goes in `PART_OVERRIDES` in
`page_generators/model_viewer.py`: `hideParts` joins the `optional` baseline
for the character (Ann's dog, which every rig leaves on but the game walks out
only for specific clips), and `clips` adds `show`/`hide` lists per clip name.
Overrides apply when the manifest is built, so tuning them needs no re-export.
`Module:ModelViewer` passes both through: per-clip `show`/`hide` on the clip
entry, and the character's `hideParts` folded into `data-hide-parts`.

## Shader notes

Channel semantics come from the shader's own property descriptions, recovered
from `shader.unity3d`:

| Property | Meaning |
|---|---|
| `_BaseMap` | Base Color (RGB) Alpha (A) |
| `_MaskMap` | Light Attenuation Adjust (R) MatCap Mask (G) Rim Mask (B) |
| `_SpecularMap` | Specular Color (RGB) |
| `_EmissionMap` | Emission Map (RGB) Animation Mask (A) |

These extras preserve the game’s material data. The local viewer uses the
gadget’s glTF rendering and outline implementation; the previous local toon
shader implementation is available in git history.

## On the wiki

`tools/model_viewer.html` runs the same **ModelViewer** gadget as the wiki,
written for
[dev.miraheze.org](https://dev.miraheze.org/wiki/Template:ModelViewer), which
turns a `.model-viewer` div's `data-` attributes into a three.js viewer and
fetches nothing until one scrolls into view.

The `.glb` files cannot live on the wiki: uploading them needs ManageWiki
changes, and a Content Security Policy limits where a page may fetch from
anyway. They go to [StellaSoraModels] on GitHub instead — the whole `actor3d`
tree, character subdirectories and all — and jsDelivr serves them from there,
which the CSP does allow.

`page_generators/model_viewer.py` records the result:

```bash
uv run -m page_generators.model_viewer
```

It writes one page: `Module:ModelViewer/data.json`, the manifest of every
model, skin and clip. Everything that reads it is maintained by hand on the
wiki — `Module:ModelViewer` and its `/doc`, a `3D models` page holding a viewer
per character, and a `3D models` section on each character's `/gallery` page,
each of them one `{{#invoke:}}`. That split is the point: exporting a character
or a skin changes the manifest and nothing else.

Variants inherit their base model's clips. When both have a clip with the
same name, the variant's own clip takes precedence. Part-visibility rules
travel with each clip, and the target model's `PART_OVERRIDES` apply after
the merge.

The manifest holds paths relative to a `base` URL rather than whole URLs.
Each model's `anims` directory is the common parent of its clip directories;
clips from multiple directories carry relative paths and explicit names.
`MODEL_REPO_REF` in that module
is the git ref jsDelivr is pointed at; jsDelivr caches a branch for 12 hours,
so a re-export that has to show up at once wants a tag or a commit sha there,
or a purge: `--purge` first purges every file the model repository's latest
commit touched, 100 paths per request.

The manifest is built from what is on disk here, so it will happily describe
models nobody has pushed; push `actor3d` first, or the viewer 404s.

Nothing here runs from `main` or `main2` yet. Pushing `actor3d` to GitHub is a
step outside the bot, and publishing a manifest ahead of it gives every viewer a
404, so this stays a job you run once the push is done — after which
`save_manifest()` belongs in `main2` next to `char_gallery_page()`.

[StellaSoraModels]: https://github.com/lihaohong6/StellaSoraModels

## Not implemented

- Weapons sit unposed in the prefab — they are socket-attached at runtime. Play
  any clip and they snap into place, because the clips animate their sockets.
- Size is unoptimised: textures are embedded as PNG. WebP or KTX2 plus Draco or
  meshopt should get a character from ~4 MB to under ~1 MB for wiki use. It is
  the wiki that makes this worth doing: a character page pulls 4.5 MB before a
  reader sees anything.
- The ModelViewer gadget is not installed on stellasora.miraheze.org. It needs
  `MediaWiki:Gadget-ModelViewer.js` (one `mw.loader.load` of the dist bundle,
  as on the dev wiki) and an entry in `MediaWiki:Gadgets-definition`, both of
  which want an interface admin rather than the bot.
- Only Amber, Donna and Nazuka are on GitHub so far — 191 of the 1,930 files
  the manifest names.
