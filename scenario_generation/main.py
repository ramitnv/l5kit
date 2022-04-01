import os
import subprocess
import pickle
import l5kit.configs as l5kit_configs
import l5kit.data as l5kit_data
import l5kit.dataset as l5kit_dataset
import l5kit.simulation.dataset as simulation_dataset
import l5kit.vectorization.vectorizer_builder as vectorizer_builder
from extract_scenario_dataset import process_scenes_data
from pathlib import Path
import h5py
import argparse

# example use: $ python -m main --config_file_name config_full --source_name train_data_loader
########################################################################
parser = argparse.ArgumentParser()
parser.add_argument('--config_file_name', type=str,
                    default='config_sample',
                    help=" 'config_sample' | 'config_full' ")
parser.add_argument('--source_name', type=str,
                    default='train_data_loader',
                    help=' "train_data_loader | "val_data_loader" ')
parser.add_argument('--verbose', type=int,
                    default=0,
                    help=" 0 | 1 ")
args = parser.parse_args()

save_dir_name = 'l5kit_data_' + args.config_file_name + '_' + args.source_name
config_file = str(Path.cwd() / "configs" / args.config_file_name) + ".yaml"
dataset_path = open(Path.cwd().parent / "dataset_dir.txt", "r").read().strip()
start_frame_index = 2  # the time frame to use from the simulator, 1 good

max_n_agents = 8  # we will use up to max_n_agents agents only from the data
min_n_agents = 2  # we will discard scenes with less valid agents
min_extent_length = 3  # [m] - discard shorter agents
min_extent_width = 1  # [m] - discard narrower agents
max_distance_map = 40   # [m] - we will discard any map points farther than max_distance_map from the ego
max_distance_agent = 30   # [m] - we will discard any agents with centroid farther than max_distance_map from the ego
# Our changes to config file:
# max_retrieval_distance_m: 40  # maximum radius around the AoI for which we retrieve
# max_agents_distance: 40 # maximum distance from AoI for another agent to be picked
# filter_agents_threshold: 0.0
# max_agents_distance: 80
# train_data_loader key

########################################################################
save_folder = 'AVSG_Data'
save_dir_path = os.path.join(save_folder, save_dir_name)

if not os.path.exists(save_folder):
    os.mkdir(save_folder)

if os.path.exists(save_dir_path):
    print(f'Save path {save_dir_path} already exists, will be override...')
else:
    os.mkdir(save_dir_path)

save_info_file_path = Path(save_dir_path, 'info').with_suffix('.pkl')
save_data_file_path = Path(save_dir_path, 'data').with_suffix('.h5')

########################################################################
# Load data and configurations
########################################################################
# set env variable for data
os.environ["L5KIT_DATA_FOLDER"] = dataset_path
dm = l5kit_data.LocalDataManager(None)
cfg = l5kit_configs.load_config_data(config_file)

dataset_cfg = cfg[args.source_name]

dataset_zarr = l5kit_data.ChunkedDataset(dm.require(dataset_cfg["key"])).open()
n_scenes = len(dataset_zarr.scenes)
vectorizer = vectorizer_builder.build_vectorizer(cfg, dm)
dataset = l5kit_dataset.EgoDatasetVectorized(cfg, dataset_zarr, vectorizer)

print(dataset)
print(f'Dataset source: {cfg[args.source_name]["key"]}, number of scenes total: {n_scenes}')

num_simulation_steps = 10
sim_cfg = simulation_dataset.SimulationConfig(use_ego_gt=False, use_agents_gt=False, disable_new_agents=True,
                                              distance_th_far=500, distance_th_close=50,
                                              num_simulation_steps=num_simulation_steps,
                                              start_frame_index=start_frame_index, show_info=True)

scene_indices = list(range(n_scenes))
# scene_indices = [39]

saved_mats, dataset_props = process_scenes_data(
    scene_indices, dataset, dataset_zarr, dm, sim_cfg, cfg, min_n_agents, max_n_agents, min_extent_length,
    min_extent_width, max_distance_map, max_distance_agent, verbose=args.verbose)

n_scenes = dataset_props['n_scenes']
git_version = subprocess.check_output(["git", "describe", "--always"]).strip().decode()

saved_mats_info = {}
with h5py.File(save_data_file_path, 'w') as h5f:
    for var_name, var in saved_mats.items():
        my_ds = h5f.create_dataset(var_name, data=var.data)
        if 'agents' in var_name:
            entity = 'agents'
        else:
            entity = 'map'
        saved_mats_info[var_name] = {'dtype': var.dtype,
                                     'shape': var.shape,
                                     'entity': entity}

with open(save_info_file_path, 'wb') as fid:
    pickle.dump({'dataset_props': dataset_props, 'saved_mats_info': saved_mats_info,
                 'git_version': git_version}, fid)

print(f'Saved data of {n_scenes} valid scenes our of {len(scene_indices)} scenes at ', save_dir_path)
