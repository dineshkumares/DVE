import json
import copy
import argparse
import itertools
from pathlib import Path
from collections import OrderedDict


def generate_configs(base_config, dest_dir, embeddings, grid, refresh, ckpts_path):
    with open(base_config, "r") as f:
        base = json.load(f)

    with open(ckpts_path, "r") as f:
        ckpts = json.load(f)

    model_family = {
        "smallnet": {"preproc": {"crop": 15, "imwidth": 100}, "name": "SmallNet"},
        "hourglass": {"preproc": {"crop": 20, "imwidth": 136}, "name": "HourglassNet"},
    }

    for model_name in embeddings:

        # model naming convention: <dataset-tokens>-<model_type>-<embedding-dim>-<dve>
        tokens = model_name.split("-")
        if tokens[-1] == "dve":
            tokens.pop()  # remove dve flag if present to use relative negative offsets
        model_type, embedding_dim = tokens[-2], int(tokens[-1][:-1])
        preproc_kwargs = model_family[model_type]["preproc"]
        
        hparam_vals = [x for x in grid.values()]
        grid_vals = list(itertools.product(*hparam_vals))
        hparams = list(grid.keys())
        epoch = ckpts[model_name]["epoch"]

        for cfg_vals in grid_vals:
            # dest_name = Path(base_config).stem
            config = copy.deepcopy(base)
            for hparam, val in zip(hparams, cfg_vals):
                if hparam == "smax":
                    config["keypoint_regressor"]["softmaxarg_mul"] = val
                elif hparam == "lr":
                    config["optimizer"]["args"]["lr"] = val
                elif hparam == "bs":
                    val = int(val)
                    config["batch_size"] = val
                elif hparam == "upsample":
                    val = bool(val)
                    config["keypoint_regressor_upsample"] = val
                else:
                    raise ValueError(f"unknown hparam: {hparam}")
            ckpt = f"checkpoint-epoch{epoch}.pth"
            timestamp = ckpts[model_name]["timestamp"]
            ckpt_path = Path("data/saved/models") / model_name / timestamp / ckpt
            config["arch"]["type"] = model_family[model_type]["name"]
            config["arch"]["args"]["num_output_channels"] = embedding_dim
            config["dataset"]["args"].update(preproc_kwargs)
            config["finetune_from"] = str(ckpt_path)
            if "-ft" in str(dest_dir):
                loss = "dense_correlation_loss"
                if "dve" in model_name:
                    loss += "_dve"
                config["loss"] = loss
                # avoid OOM for hourglass
                if "hourglass" in model_name:
                    config["batch_size"] = 16

            dest_path = Path(dest_dir) / f"{model_name}.json"
            dest_path.parent.mkdir(exist_ok=True, parents=True)
            if not dest_path.exists() or refresh:
                with open(str(dest_path), "w") as f:
                    json.dump(config, f, indent=4, sort_keys=False)
            else:
                print(f"config file at {str(dest_path)} exists, skipping....")
        print(f"Wrote {len(grid_vals)} configs to disk")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpts_path", default="misc/server-checkpoints.json")
    parser.add_argument('--bs', default="32")
    parser.add_argument('--smax', default="100")
    parser.add_argument('--lr', default="1E-3")
    parser.add_argument('--upsample', default="0")
    parser.add_argument('--refresh', action="store_true")
    parser.add_argument('--target', default="mafl-keypoints",
                        choices=["mafl-keypoints", "aflw-keypoints", "aflw-ft",
                                 "aflw-mtfl-ft", "aflw-ft-keypoints",
                                 "aflw-mtfl-ft-keypoints"])
    args = parser.parse_args()

    grid_args = OrderedDict()
    keys = ["lr", "bs"]
    if "keypoints" in args.target:
        keys += ["smax", "upsample"]

    for key in keys:
        grid_args[key] = [float(x) for x in getattr(args, key).split(",")]
    dest_config_dir = Path("configs") / args.target
    base_config_path = Path("configs/templates") / f"{args.target}.json"

    pretrained_embeddings = [
        "celeba-smallnet-3d",
        "celeba-smallnet-16d",
        "celeba-smallnet-32d",
        "celeba-smallnet-64d",
        "celeba-smallnet-3d-dve",
        "celeba-smallnet-16d-dve",
        "celeba-smallnet-32d-dve",
        "celeba-smallnet-64d-dve",
        "celeba-hourglass-64d-dve",
    ]

    if "-ft-keypoints" in args.target:
        prefix = args.target.replace("-keypoints", "")
        pretrained_embeddings = [f"{prefix}-{x}" for x in pretrained_embeddings]

    generate_configs(
        base_config=base_config_path,
        embeddings=pretrained_embeddings,
        ckpts_path=args.ckpts_path,
        refresh=args.refresh,
        dest_dir=dest_config_dir,
        grid=grid_args,
    )
