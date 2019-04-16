"""From: https://gist.github.com/alexlee-gk/38916bf524dc75ca1b988d113aa30710"""

import os
import numpy as np


def save_gif(gif_fname, images, fps=4):
    """
    To generate a gif from image files, first generate palette from images
    and then generate the gif from the images and the palette.
    ffmpeg -i input_%02d.jpg -vf palettegen -y palette.png
    ffmpeg -i input_%02d.jpg -i palette.png -lavfi paletteuse -y output.gif
    Alternatively, use a filter to map the input images to both the palette
    and gif commands, while also passing the palette to the gif command.
    ffmpeg -i input_%02d.jpg -filter_complex "[0:v]split[x][z];[z]palettegen[y];[x][y]paletteuse" -y output.gif
    To directly pass in numpy images, use rawvideo format and `-i -` option.
    """
    from subprocess import Popen, PIPE
    head, tail = os.path.split(gif_fname)
    if head and not os.path.exists(head):
        os.makedirs(head, exist_ok=True)
    cmd = ['ffmpeg', '-y',
           '-f', 'rawvideo',
           '-vcodec', 'rawvideo',
           '-r', '%.02f' % fps,
           '-s', '%dx%d' % (images[0].shape[1], images[0].shape[0]),
           '-pix_fmt', 'rgb24',
           '-i', '-',
           '-filter_complex', '[0:v]split[x][z];[z]palettegen[y];[x]fifo[x];[x][y]paletteuse',
           '%s' % gif_fname]
    proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    for image in images:
        proc.stdin.write(image.tostring())
    out, err = proc.communicate()
    if proc.returncode:
        err = '\n'.join([' '.join(cmd), err.decode('utf8')])
        raise IOError(err)
    del proc


def encode_gif(images, fps=4):
    from subprocess import Popen, PIPE
    cmd = ['ffmpeg', '-y',
           '-f', 'rawvideo',
           '-vcodec', 'rawvideo',
           '-r', '%.02f' % fps,
           '-s', '%dx%d' % (images[0].shape[1], images[0].shape[0]),
           '-pix_fmt', 'rgb24',
           '-i', '-',
           '-filter_complex', '[0:v]split[x][z];[z]palettegen[y];[x]fifo[x];[x][y]paletteuse',
           '-r', '%.02f' % fps,
           '-f', 'gif',
           '-']
    proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    for image in images:
        proc.stdin.write(image.tostring())
    out, err = proc.communicate()
    if proc.returncode:
        err = '\n'.join([' '.join(cmd), err.decode('utf8')])
        raise IOError(err)
    del proc
    return out


def main():
    images_shape = (128, 64, 64, 3)  # num_frames, height, width, channels
    images = np.random.randint(256, size=images_shape).astype(np.uint8)

    save_gif('output_save.gif', images)
    with open('output_save.gif', 'rb') as f:
        string_save = f.read()

    string_encode = encode_gif(images)
    with open('output_encode.gif', 'wb') as f:
        f.write(string_encode)

    print(np.all(string_save == string_encode))


if __name__ == '__main__':
    main()
