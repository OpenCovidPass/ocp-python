import wand.image
import qrcode
import sys
import hashlib
import base64
import bz2

def generate_qr(data: bytes):
  qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=20, border=4)
  qr.add_data(data)
  return qr.make_image(fill_color="black", back_color="white")

def compress_img(filename: str, output: str):
  img = wand.image.Image(filename=filename)
  sq = min(img.size[0], img.size[1])
  img.crop(width=sq, height=sq, gravity="center")
  img.resize(200, 200)
  img.quantize(8, "gray")
  img.save(filename=output)

def chunk_data(data: bytes):
  data = base64.b32encode(data).decode().rstrip('=')
  number = 6
  chunk_size = len(data) // number
  if (number > 10):
    raise Exception("Too much data to store in qr codes!")
  return [f'{i}{number - 1}' + data[i * chunk_size: (i+1) * chunk_size] for i in range(number)]

def encode(compressed, sig, out):
  if len(sig) != 128:
    raise Exception("Invalid signature size")
  chunks = chunk_data(base64.b16decode(sig.upper()) + compressed)
  for i in range(len(chunks)):
    generate_qr(chunks[i]).save(f"{out}/{i}.png")


# MAIN CODE
input_pici = sys.argv[1]
output_pici = sys.argv[2]
output_qrs = sys.argv[3]

compress_img(input_pici, output_pici)
with open(output_pici, "rb") as file:
  data = bz2.compress(file.read(), 9)
  print(hashlib.sha256(data).hexdigest())
  sig = input("Signature: ")
  encode(data, sig, output_qrs)
