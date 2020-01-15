"""
A convenience script to playback random demonstrations from
a set of demonstrations stored in a hdf5 file.

Arguments:
    --folder (str): Path to demonstrations
    --use_actions (optional): If this flag is provided, the actions are played back
        through the MuJoCo simulator, instead of loading the simulator states
        one by one.

Example:
    $ python playback_demonstrations_from_hdf5.py --folder ../models/assets/demonstrations/SawyerPickPlace/
"""
import os
import h5py
import argparse
import random
import numpy as np

import robosuite
from robosuite.wrappers import IKWrapper
from robosuite.utils.mjcf_utils import postprocess_model_xml

from robosuite.utils.ffmpeg_gif import save_gif


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--folder",
        type=str,
        default=os.path.join(
            robosuite.models.assets_root, "demonstrations/SawyerNutAssembly"
        ),
    )
    parser.add_argument(
        "--use_actions",
        action='store_true',
    )
    parser.add_argument(
        "--ds",
        action='store_true',
        default = False
    )
    parser.add_argument(
        "--ik",
        action='store_true',
        default=True
    )
    args = parser.parse_args()

    demo_path = args.folder
    if args.ds:
        hdf5_path = os.path.join(demo_path, "demo_ds.hdf5")
    else:
        hdf5_path = os.path.join(demo_path, "demo.hdf5")
    f = h5py.File(hdf5_path, "r")
    env_name = f["data"].attrs["env"]

    env = robosuite.make(
        env_name,
        has_renderer=False,
        ignore_done=True,
        use_camera_obs=True,
        use_object_obs=False,
        camera_height=64,
        camera_width=64,
        control_freq=100,
    )

    if args.ik:
        env = IKWrapper(env)

    # list of all demonstrations episodes
    demos = list(f["data"].keys())

    if True:
        print("Playing back random episode... (press ESC to quit)")

        # # select an episode randomly
        ep = random.choice(demos)

        # read the model xml, using the metadata stored in the attribute for this episode
        model_file = f["data/{}".format(ep)].attrs["model_file"]
        model_path = os.path.join(demo_path, "models", model_file)
        with open(model_path, "r") as model_f:
            model_xml = model_f.read()

        env.reset()
        xml = postprocess_model_xml(model_xml)
        env.reset_from_xml_string(xml)
        env.sim.reset()
        # env.viewer.set_camera(0)

        # load the flattened mujoco states
        states = f["data/{}/states".format(ep)].value


        # load the initial state
        env.sim.set_state_from_flattened(states[0])
        env.sim.forward()

        # load the actions and play them back open-loop
        jvels = f["data/{}/joint_velocities".format(ep)].value
        grip_acts = f["data/{}/gripper_actuations".format(ep)].value
        actions = np.concatenate([jvels, grip_acts], axis=1)

        if args.ik:
            dpos = f["data/{}/right_dpos".format(ep)].value
            dquat = f["data/{}/right_dquat".format(ep)].value
            grip_acts = f["data/{}/gripper_actuations".format(ep)].value
            actions = np.concatenate([dpos, dquat, grip_acts], axis=1)

        num_actions = actions.shape[0]
        print(num_actions)

        frames = []
        for j, action in enumerate(actions):
            if j % 50 == 0:
                obs = env._get_observation()
                frame = obs["image"][::-1]
                frames.append(frame)

            env.step(action)
            # env.render()

            print(j)

            if j < num_actions - 1:

                # ensure that the actions deterministically lead to the same recorded states
                state_playback = env.sim.get_state().flatten()
                # assert(np.all(np.equal(states[j + 1], state_playback)))

            # if j == 300:
            #     break

        save_gif("out.gif", frames, fps=30)

    f.close()