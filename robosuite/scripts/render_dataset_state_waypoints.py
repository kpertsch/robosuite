
import argparse
import h5py
import random
import os
import numpy as np
import tqdm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
#import seaborn

import robosuite
from robosuite.utils.mjcf_utils import postprocess_model_xml
from robosuite import make
from robosuite.utils.ffmpeg_gif import save_gif

from robosuite.utils.transform_utils import mat2pose, quat_multiply, quat_conjugate
from robosuite.environments.base import make_invkin_env

from robosuite.utils.transform_utils import quat_slerp

def compute_fwd_kinematics(des_state, orig_state):
    env.sim.set_state_from_flattened(des_state)
    env.sim.forward()
    des_state_pose = env._right_hand_pose

    # reset to orig state
    env.sim.set_state_from_flattened(orig_state)
    env.sim.forward()

    return des_state_pose


def compute_pose_difference(des_pose, current_pose):
    """
    :param des_pose:
    :param current_pose:
    :return:

    compute diff transform so that

    current_pose * diff  = des_pose
    diff = des_pose * inv(current_pose)
    """

    des_pos, des_quat = mat2pose(des_pose)
    curr_pos, curr_quat = mat2pose(current_pose)

    dpos = des_pos - curr_pos
    diff = quat_multiply(des_quat, quat_conjugate(curr_quat))
    return dpos, diff


def render(args, f, env):
    demos = list(f["data"].keys())
    for key in tqdm.tqdm(demos):
        # read the model xml, using the metadata stored in the attribute for this episode
        model_file = f["data/{}".format(key)].attrs["model_file"]
        model_path = os.path.join(args.demo_folder, "models", model_file)
        with open(model_path, "r") as model_f:
            model_xml = model_f.read()

        env.reset()
        xml = postprocess_model_xml(model_xml)
        env.reset_from_xml_string(xml)
        env.sim.reset()


        # load + subsample data
        states, _ = FixedFreqSubsampler(n_skip=args.skip_frame)(f["data/{}/states".format(key)].value)
        # d_pos, _ = FixedFreqSubsampler(n_skip=args.skip_frame, aggregator=SumAggregator()) \
        #             (f["data/{}/right_dpos".format(key)].value, aggregate=True)
        # d_quat, _ = FixedFreqSubsampler(n_skip=args.skip_frame, aggregator=QuaternionAggregator()) \
        #              (f["data/{}/right_dquat".format(key)].value, aggregate=True)
        gripper_actuation, _ = FixedFreqSubsampler(n_skip=args.skip_frame)(f["data/{}/gripper_actuations".format(key)].value)
        joint_velocities, _ = FixedFreqSubsampler(n_skip=args.skip_frame, aggregator=SumAggregator()) \
                                (f["data/{}/joint_velocities".format(key)].value, aggregate=True)

        n_steps = states.shape[0]
        if args.target_length is not None and n_steps > args.target_length:
            continue


        frames = []
        achieved_states = []
        delta_actions = []

        env.sim.set_state_from_flattened(states[0])
        env.sim.forward()

        obs = env._get_observation()
        frame = obs["image"][::-1]
        frames.append(frame)

        states = states[1:]

        current_eefpose = env._right_hand_pose
        _, first_quat = mat2pose(current_eefpose)

        print('total number of steps after downsampling', states.shape[0])
        for i, state in enumerate(states):
            obs = env._get_observation()
            frame = obs["image"][::-1]
            frames.append(frame)

            current_eefpose = env._right_hand_pose
            _, curr_quat = mat2pose(current_eefpose)
            des_eefpose = compute_fwd_kinematics(state, env.sim.get_state().flatten())
            _, des_quat = mat2pose(des_eefpose)

            d_pos, d_quat = compute_pose_difference(des_eefpose, current_eefpose)

            print('curr eefpos {}, des_eefpos {}, dpos {}, d_quat {}'.format(mat2pose(current_eefpose)[0],
                                                                  mat2pose(des_eefpose)[0],
                                                                  d_pos, d_quat))
            # print("inv kin. error: ", env.controller._get_current_error())

            ## debug:
            zero_quat = np.array([0, 0, 0, 1.])

            n_substeps = 10
            delta_actions.append(np.concatenate((d_pos, d_quat, gripper_actuation[i]), axis=-1))
            for s in range(n_substeps):
                env.step(np.concatenate((d_pos/n_substeps, zero_quat, gripper_actuation[i]), axis=-1))
                # env.step(np.concatenate((d_pos/n_substeps, quat_slerp(zero_quat, d_quat, s/n_substeps), gripper_actuation[i]), axis=-1))
                # env.step(np.concatenate((d_pos/n_substeps, quat_slerp(curr_quat, des_quat, s/n_substeps), gripper_actuation[i]), axis=-1))

            print('step ', i)

            #todo debug:
            if i == 20:
                break

        frames = np.stack(frames, axis=0)
        delta_actions = np.stack(delta_actions, axis=-1)

        pad_mask = np.ones((n_steps,)) if n_steps == args.target_length \
                        else np.concatenate((np.ones((n_steps,)), np.zeros((args.target_length - n_steps,))))

        h5_path = os.path.join(args.output_path, "seq_{}.h5".format(key))
        with h5py.File(h5_path, 'w') as F:
            F['traj_per_file'] = 1
            F["traj0/images"] = frames
            F["traj0/actions"] = delta_actions
            F["traj0/states"] = achieved_states
            F["traj0/pad_mask"] = pad_mask
            F["traj0/joint_velocities"] = joint_velocities

        xml_path = os.path.join(args.output_path, "seq_{}.xml".format(key))
        env.model.save_model(xml_path)

        fig_file_name = os.path.join(args.output_path, "seq_{}".format(key))
        save_gif(fig_file_name + ".gif", frames, fps=15)

        import pdb; pdb.set_trace()


def steps2length(steps):
    return steps/(10*15)


def plot_stats(args, file):
    # plot histogram of lengths
    demos = list(file["data"].keys())

    used_keys = list(file["data/demo_1"].keys())
    import pdb; pdb.set_trace()
    lengths = []
    for key in tqdm.tqdm(demos):
        states = file["data/{}/states".format(key)].value
        lengths.append(states.shape[0])
    lengths = np.stack(lengths)
    fig = plt.figure()
    plt.hist(lengths, bins=30)
    plt.xlabel("Approx. Demo Length [sec]")
    # plt.title("Peg Assembly")
    # plt.xlim(5, 75)
    # plt.ylim(0, 165)
    fig.savefig(os.path.join(args.output_path, "length_hist.png"))
    plt.close()


class DataSubsampler:
    def __init__(self, aggregator):
        self._aggregator = aggregator

    def __call__(self, *args, **kwargs):
        raise NotImplementedError("This function needs to be implemented by sub-classes!")


class FixedFreqSubsampler(DataSubsampler):
    """Subsamples input array's first dimension by skipping given number of frames."""
    def __init__(self, n_skip, aggregator=None):
        super().__init__(aggregator)
        self._n_skip = n_skip

    def __call__(self, val, idxs=None, aggregate=False):
        """Subsamples with idxs if given, aggregates with aggregator if aggregate=True."""
        if self._n_skip == 0:
            return val, None

        if idxs is None:
            seq_len = val.shape[0]
            idxs = np.arange(0, seq_len - 1, self._n_skip + 1)

        if aggregate:
            assert self._aggregator is not None     # no aggregator given!
            return self._aggregator(val, idxs), idxs
        else:
            return val[idxs], idxs


class Aggregator:
    def __call__(self, *args, **kwargs):
        raise NotImplementedError("This function needs to be implemented by sub-classes!")


class SumAggregator(Aggregator):
    def __call__(self, val, idxs):
        return np.add.reduceat(val, idxs, axis=0)


class QuaternionAggregator(Aggregator):
    def __call__(self, val, idxs):
        # quaternions get aggregated by multiplying in order
        aggregated = [val[0]]
        for i in range(len(idxs)-1):
            idx, next_idx = idxs[i], idxs[i+1]
            agg_val = val[idx]
            for ii in range(idx+1, next_idx):
                agg_val = self.quaternion_multiply(agg_val, val[ii])
            aggregated.append(agg_val)
        return np.asarray(aggregated)

    @staticmethod
    def quaternion_multiply(Q0, Q1):
        w0, x0, y0, z0 = Q0
        w1, x1, y1, z1 = Q1
        return np.array([-x1 * x0 - y1 * y0 - z1 * z0 + w1 * w0,
                         x1 * w0 + y1 * z0 - z1 * y0 + w1 * x0,
                         -x1 * z0 + y1 * w0 + z1 * x0 + w1 * y0,
                         x1 * y0 - y1 * x0 + z1 * w0 + w1 * z0], dtype=np.float64)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--demo_folder", type=str,
                        default=os.path.join(robosuite.models.assets_root, "demonstrations/SawyerNutAssembly"))
    parser.add_argument("--output_path", type=str, default=".")
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--skip_frame", type=int, default=0)
    parser.add_argument("--gen_dataset", type=bool, default=False)
    parser.add_argument("--plot_stats", type=bool, default=False)
    parser.add_argument("--target_length", type=int, default=-1)
    args = parser.parse_args()

    if args.target_length == -1:
       args.target_length = None

    # initialize an environment with offscreen renderer
    demo_file = os.path.join(args.demo_folder, "demo.hdf5")
    f = h5py.File(demo_file, "r")

    env_name = f["data"].attrs["env"]

    env = make_invkin_env(
        env_name,
        has_renderer=False,
        ignore_done=True,
        use_camera_obs=True,
        use_object_obs=False,
        camera_height=args.height,
        camera_width=args.width,
    )
    if not os.path.exists(args.output_path):
        os.makedirs(args.output_path)

    if args.gen_dataset:
        render(args, f, env)

    if args.plot_stats:
        plot_stats(args, f)

    print("Done")
    f.close()






