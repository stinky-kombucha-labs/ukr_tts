# Vendored code

`ukrainian_tts/` is a vendored copy of the TTS engine from
[robinhad/ukrainian-tts](https://github.com/robinhad/ukrainian-tts)
(see `LICENSE` in this folder). Do not edit it here; update by copying a newer
upstream release.

Model weights are not stored in git. On first run the engine downloads them
(release `v6.0.0`, ~430 MB) into `models/`: `model.pth`, `config.yaml`,
`spk_xvector.ark`, `feats_stats.npz`.
