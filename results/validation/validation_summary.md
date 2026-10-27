# Numerical validation

Outputs of the row-major traversal (all traversals are bit-identical, see tests) compared with an independent float64 NumPy transcription of the documented formulas and with OpenCV 4.12.0 `cvtColor` on float32 input. Errors are absolute, in output units (H in degrees, L in 0..100).

| image | op | reference | channel | max abs err | mean abs err | tolerance | pass |
|---|---|---|---|---|---|---|---|
| photo 512x512 | unpack | numpy64 | R | 7.433e-08 | 2.121e-08 | 1.00e-07 | yes |
| photo 512x512 | unpack | numpy64 | G | 7.433e-08 | 1.609e-08 | 1.00e-07 | yes |
| photo 512x512 | unpack | numpy64 | B | 7.433e-08 | 2.075e-08 | 1.00e-07 | yes |
| photo 512x512 | unpack | opencv | R | 5.960e-08 | 1.528e-08 | 1.00e-07 | yes |
| photo 512x512 | unpack | opencv | G | 5.960e-08 | 7.884e-09 | 1.00e-07 | yes |
| photo 512x512 | unpack | opencv | B | 5.960e-08 | 1.327e-08 | 1.00e-07 | yes |
| photo 512x512 | yuv | numpy64 | Y | 1.645e-07 | 2.115e-08 | 3.00e-07 | yes |
| photo 512x512 | yuv | numpy64 | U | 9.519e-08 | 1.698e-08 | 3.00e-07 | yes |
| photo 512x512 | yuv | numpy64 | V | 1.451e-07 | 1.730e-08 | 3.00e-07 | yes |
| photo 512x512 | yuv | opencv | Y | 1.788e-07 | 1.322e-08 | 1.00e-06 | yes |
| photo 512x512 | yuv | opencv | U | 1.192e-07 | 1.018e-08 | 1.00e-06 | yes |
| photo 512x512 | yuv | opencv | V | 1.192e-07 | 1.391e-08 | 1.00e-06 | yes |
| photo 512x512 | hsv | numpy64 | H | 2.441e-04 | 3.418e-06 | 2.00e-03 | yes |
| photo 512x512 | hsv | numpy64 | S | 8.877e-08 | 2.113e-08 | 1.00e-06 | yes |
| photo 512x512 | hsv | numpy64 | V | 7.433e-08 | 2.737e-08 | 1.00e-06 | yes |
| photo 512x512 | hsv | opencv | H | 1.831e-03 | 4.854e-05 | 1.09e-02 | yes |
| photo 512x512 | hsv | opencv | S | 3.040e-05 | 2.811e-07 | 3.04e-05 | yes |
| photo 512x512 | hsv | opencv | V | 5.960e-08 | 1.941e-08 | 1.00e-06 | yes |
| photo 512x512 | lab | numpy64 | L | 1.512e-05 | 1.888e-06 | 1.00e-03 | yes |
| photo 512x512 | lab | numpy64 | a | 9.619e-05 | 1.046e-05 | 1.00e-03 | yes |
| photo 512x512 | lab | numpy64 | b | 3.377e-05 | 4.028e-06 | 1.00e-03 | yes |
| photo 512x512 | lab | opencv | L | 1.829e-01 | 6.459e-02 | n/a | n/a |
| photo 512x512 | lab | opencv | a | 4.167e-01 | 8.790e-02 | n/a | n/a |
| photo 512x512 | lab | opencv | b | 3.236e-01 | 9.697e-02 | n/a | n/a |
| noise 512x512 | unpack | numpy64 | R | 7.433e-08 | 2.958e-08 | 1.00e-07 | yes |
| noise 512x512 | unpack | numpy64 | G | 7.433e-08 | 2.950e-08 | 1.00e-07 | yes |
| noise 512x512 | unpack | numpy64 | B | 7.433e-08 | 2.947e-08 | 1.00e-07 | yes |
| noise 512x512 | unpack | opencv | R | 5.960e-08 | 1.963e-08 | 1.00e-07 | yes |
| noise 512x512 | unpack | opencv | G | 5.960e-08 | 1.955e-08 | 1.00e-07 | yes |
| noise 512x512 | unpack | opencv | B | 5.960e-08 | 1.954e-08 | 1.00e-07 | yes |
| noise 512x512 | yuv | numpy64 | Y | 1.674e-07 | 3.379e-08 | 3.00e-07 | yes |
| noise 512x512 | yuv | numpy64 | U | 1.029e-07 | 2.036e-08 | 3.00e-07 | yes |
| noise 512x512 | yuv | numpy64 | V | 1.597e-07 | 2.355e-08 | 3.00e-07 | yes |
| noise 512x512 | yuv | opencv | Y | 1.788e-07 | 2.297e-08 | 1.00e-06 | yes |
| noise 512x512 | yuv | opencv | U | 1.192e-07 | 1.516e-08 | 1.00e-06 | yes |
| noise 512x512 | yuv | opencv | V | 2.384e-07 | 2.354e-08 | 1.00e-06 | yes |
| noise 512x512 | hsv | numpy64 | H | 1.526e-04 | 4.469e-06 | 2.00e-03 | yes |
| noise 512x512 | hsv | numpy64 | S | 8.877e-08 | 2.157e-08 | 1.00e-06 | yes |
| noise 512x512 | hsv | numpy64 | V | 7.433e-08 | 4.690e-08 | 1.00e-06 | yes |
| noise 512x512 | hsv | opencv | H | 1.831e-03 | 1.027e-05 | 1.09e-02 | yes |
| noise 512x512 | hsv | opencv | S | 7.570e-06 | 1.247e-07 | 3.04e-05 | yes |
| noise 512x512 | hsv | opencv | V | 5.960e-08 | 3.602e-08 | 1.00e-06 | yes |
| noise 512x512 | lab | numpy64 | L | 1.709e-05 | 2.885e-06 | 1.00e-03 | yes |
| noise 512x512 | lab | numpy64 | a | 9.632e-05 | 1.631e-05 | 1.00e-03 | yes |
| noise 512x512 | lab | numpy64 | b | 3.725e-05 | 5.966e-06 | 1.00e-03 | yes |
| noise 512x512 | lab | opencv | L | 1.858e-01 | 8.619e-02 | n/a | n/a |
| noise 512x512 | lab | opencv | a | 4.269e-01 | 8.025e-02 | n/a | n/a |
| noise 512x512 | lab | opencv | b | 3.091e-01 | 7.927e-02 | n/a | n/a |
| gradient 512x512 | unpack | numpy64 | R | 7.433e-08 | 2.957e-08 | 1.00e-07 | yes |
| gradient 512x512 | unpack | numpy64 | G | 7.433e-08 | 2.957e-08 | 1.00e-07 | yes |
| gradient 512x512 | unpack | numpy64 | B | 7.433e-08 | 2.767e-08 | 1.00e-07 | yes |
| gradient 512x512 | unpack | opencv | R | 5.960e-08 | 1.963e-08 | 1.00e-07 | yes |
| gradient 512x512 | unpack | opencv | G | 5.960e-08 | 1.963e-08 | 1.00e-07 | yes |
| gradient 512x512 | unpack | opencv | B | 5.960e-08 | 1.486e-08 | 1.00e-07 | yes |
| gradient 512x512 | yuv | numpy64 | Y | 1.515e-07 | 3.374e-08 | 3.00e-07 | yes |
| gradient 512x512 | yuv | numpy64 | U | 1.015e-07 | 2.151e-08 | 3.00e-07 | yes |
| gradient 512x512 | yuv | numpy64 | V | 1.416e-07 | 2.399e-08 | 3.00e-07 | yes |
| gradient 512x512 | yuv | opencv | Y | 1.788e-07 | 2.265e-08 | 1.00e-06 | yes |
| gradient 512x512 | yuv | opencv | U | 1.192e-07 | 1.563e-08 | 1.00e-06 | yes |
| gradient 512x512 | yuv | opencv | V | 2.384e-07 | 2.398e-08 | 1.00e-06 | yes |
| gradient 512x512 | hsv | numpy64 | H | 2.219e-05 | 4.270e-06 | 2.00e-03 | yes |
| gradient 512x512 | hsv | numpy64 | S | 8.877e-08 | 2.284e-08 | 1.00e-06 | yes |
| gradient 512x512 | hsv | numpy64 | V | 7.433e-08 | 4.622e-08 | 1.00e-06 | yes |
| gradient 512x512 | hsv | opencv | H | 1.831e-03 | 8.565e-06 | 1.09e-02 | yes |
| gradient 512x512 | hsv | opencv | S | 2.384e-07 | 1.036e-07 | 3.04e-05 | yes |
| gradient 512x512 | hsv | opencv | V | 5.960e-08 | 3.303e-08 | 1.00e-06 | yes |
| gradient 512x512 | lab | numpy64 | L | 1.632e-05 | 2.934e-06 | 1.00e-03 | yes |
| gradient 512x512 | lab | numpy64 | a | 9.590e-05 | 1.685e-05 | 1.00e-03 | yes |
| gradient 512x512 | lab | numpy64 | b | 3.681e-05 | 6.264e-06 | 1.00e-03 | yes |
| gradient 512x512 | lab | opencv | L | 1.735e-01 | 8.452e-02 | n/a | n/a |
| gradient 512x512 | lab | opencv | a | 3.040e-01 | 8.053e-02 | n/a | n/a |
| gradient 512x512 | lab | opencv | b | 2.874e-01 | 7.899e-02 | n/a | n/a |
| mixed 333x217 | unpack | numpy64 | R | 7.433e-08 | 2.658e-08 | 1.00e-07 | yes |
| mixed 333x217 | unpack | numpy64 | G | 7.433e-08 | 2.535e-08 | 1.00e-07 | yes |
| mixed 333x217 | unpack | numpy64 | B | 7.433e-08 | 2.208e-08 | 1.00e-07 | yes |
| mixed 333x217 | unpack | opencv | R | 5.960e-08 | 1.624e-08 | 1.00e-07 | yes |
| mixed 333x217 | unpack | opencv | G | 5.960e-08 | 1.549e-08 | 1.00e-07 | yes |
| mixed 333x217 | unpack | opencv | B | 5.960e-08 | 1.138e-08 | 1.00e-07 | yes |
| mixed 333x217 | yuv | numpy64 | Y | 1.529e-07 | 2.830e-08 | 3.00e-07 | yes |
| mixed 333x217 | yuv | numpy64 | U | 1.012e-07 | 1.678e-08 | 3.00e-07 | yes |
| mixed 333x217 | yuv | numpy64 | V | 1.437e-07 | 2.028e-08 | 3.00e-07 | yes |
| mixed 333x217 | yuv | opencv | Y | 1.788e-07 | 1.819e-08 | 1.00e-06 | yes |
| mixed 333x217 | yuv | opencv | U | 1.192e-07 | 1.139e-08 | 1.00e-06 | yes |
| mixed 333x217 | yuv | opencv | V | 2.384e-07 | 1.880e-08 | 1.00e-06 | yes |
| mixed 333x217 | hsv | numpy64 | H | 6.975e-05 | 4.598e-06 | 2.00e-03 | yes |
| mixed 333x217 | hsv | numpy64 | S | 8.877e-08 | 2.260e-08 | 1.00e-06 | yes |
| mixed 333x217 | hsv | numpy64 | V | 7.433e-08 | 3.557e-08 | 1.00e-06 | yes |
| mixed 333x217 | hsv | opencv | H | 1.831e-03 | 1.821e-05 | 1.09e-02 | yes |
| mixed 333x217 | hsv | opencv | S | 2.801e-06 | 1.183e-07 | 3.04e-05 | yes |
| mixed 333x217 | hsv | opencv | V | 5.960e-08 | 2.288e-08 | 1.00e-06 | yes |
| mixed 333x217 | lab | numpy64 | L | 1.458e-05 | 2.583e-06 | 1.00e-03 | yes |
| mixed 333x217 | lab | numpy64 | a | 8.405e-05 | 1.458e-05 | 1.00e-03 | yes |
| mixed 333x217 | lab | numpy64 | b | 3.078e-05 | 5.300e-06 | 1.00e-03 | yes |
| mixed 333x217 | lab | opencv | L | 1.831e-01 | 9.269e-02 | n/a | n/a |
| mixed 333x217 | lab | opencv | a | 3.519e-01 | 8.364e-02 | n/a | n/a |
| mixed 333x217 | lab | opencv | b | 2.994e-01 | 8.041e-02 | n/a | n/a |

Notes on OpenCV conventions:

* **yuv**: OpenCV COLOR_RGB2YUV (float) uses the same BT.601 coefficients (0.299/0.587/0.114, U 0.492, V 0.877, offset 0.5).
* **hsv**: OpenCV adds FLT_EPSILON to denominators and multiplies by 60/C instead of dividing; differences are rounding-level.
* **lab**: OpenCV's float RGB2Lab is an approximation: re-implementing it with OpenCV's own constants (matrix 0.412453..., Xn=0.950456, Zn=1.088754, 7.787/903.3 linear segment) does NOT remove the gap, and on the grey axis the error is a sawtooth (see the characterisation below), the signature of table/interpolation-based evaluation. The gap is therefore reported, not used as a pass/fail criterion; the implementation itself is validated against the float64 reference.
* **unpack**: Normalisation c/255.

OpenCV float Lab, L* error on the grey axis (OpenCV - exact), every 16th code:

| code | 0 | 16 | 32 | 48 | 64 | 80 | 96 | 112 | 128 | 144 | 160 | 176 | 192 | 208 | 224 | 240 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| err | +0.000 | -0.023 | -0.061 | -0.084 | -0.110 | -0.136 | -0.154 | -0.175 | -0.002 | -0.023 | -0.048 | -0.071 | -0.092 | -0.114 | -0.133 | -0.149 |

Max |error| on the grey axis: 0.187 L* units.
