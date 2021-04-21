import qrcode
import sys
import tempfile
import base64
import wand.image
import zbar
from PIL import Image
import os
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
import nacl.exceptions
import hashlib
import fpdf
import pygifsicle
import zlib

def generate_qr(data: bytes):
  qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=20, border=4)
  qr.add_data(data)
  return qr.make_image(fill_color="black", back_color="white")

def compress_img(filename: str, output: str):
#  img = Image.open(filename)
#  width, height = im.size
#  if width > height:
#    diff = width - height
#    img = img.crop((diff, 0, height + diff, height))
#  elif height > width:
#    diff = width - height
 #   img = img.crop((0, diff, width, width + diff))

#  img = img.resize(

  img = wand.image.Image(filename=filename)
  sq = min(img.size[0], img.size[1])
  img.crop(width=sq, height=sq, gravity="center")
  img.resize(200, 200)
  img.quantize(8, "gray")
  img.save(filename=output)
  with open(output, "rb+") as file:
    data = file.read()
    data = zlib.compress(data, 9)
    file.seek(0)
    file.truncate(0)
    file.write(data)

qrcode_max_size = 3000 #4269 - 2 #1249 - 2 #4296 - 2

def chunk_data(data: bytes):
  data = base64.b32encode(data).decode().rstrip('=')
  number = 6 #(len(data) + qrcode_max_size - 1)//qrcode_max_size
  chunk_size = len(data) // number
  if (number > 10):
    raise Exception("Too much data to store in qr codes!")
  return [f'{i}{number - 1}' + data[i * chunk_size: (i+1) * chunk_size] for i in range(number)]

def handle_decode(results):
  dats = {}
  number = -1
  for i in results:
    if len(i.data) < 2:
      continue
    idx = int(i.data[0])
    number = int(i.data[1])
    dats[idx] = i.data[2:]
  return dats, number

def load_data(input_file: str):
  scanner = zbar.ImageScanner()
  pil = Image.open(input_file).convert('L')

  width, height = pil.size
  raw = pil.tobytes()
  image = zbar.Image(width, height, 'Y800', raw)
  results = scanner.scan(image)
  scanner.set_config(0, 4)

  return handle_decode(image)

def keygen():
  priv = SigningKey.generate()
  return priv.encode(encoder=HexEncoder).decode(), priv.verify_key.encode(encoder=HexEncoder).decode()

def sign(hash, priv):
  return base64.b16encode(SigningKey(priv.encode(), encoder=HexEncoder).sign(base64.b16decode(hash.upper())))[:128].decode()

def encode(compressed, sig, out):
  if len(sig) != 128:
    raise Exception("Invalid signature size")
  chunks = chunk_data(base64.b16decode(sig.upper()) + compressed)
  for i in range(len(chunks)):
    generate_qr(chunks[i]).save(f"{out}/{i}.png")

def check(hash: str, sig: str, pubkey: str):
  try:
    VerifyKey(pubkey.encode(), encoder=HexEncoder).verify(base64.b16decode(hash.upper()), base64.b16decode(sig.encode().upper()))
    return True
  except nacl.exceptions.BadSignatureError:
    return False

def decode(qrs):
  state = {}
  number = -1

  for i in qrs:
    print(i)
    dats, new_number = load_data(i)
    if (new_number < 0):
      continue
    elif number < 0:
      number = new_number
    elif new_number != number:
      raise Exception("Mismatched QR codes")
    state.update(dats)
    missing = {i for i in range(number + 1)} - set(state.keys())
    print(missing)
    if not missing:
      break


  if number < 0:
    return set()

  if missing:
    return missing

  res = "".join([state[i] for i in range(number + 1)])
  res = res.ljust(((len(res) + 7) // 8) * 8, '=')
  res = base64.b32decode(res)

  return base64.b16encode(res[:64]).decode(),zlib.decompress(res[64:])

def decodecam(dev = None):
  state = {}
  number = -1

  proc = zbar.Processor()
  if dev is not None:
    proc.init(dev)
  else:
    proc.init()
  proc.visible = True

  missing = set()

  while True:
    proc.process_one()
    dats, new_number = handle_decode(proc.results)
    if (new_number < 0):
      continue
    elif number < 0:
      number = new_number
    elif new_number != number:
      raise Exception("Mismatched QR codes")
    state.update(dats)
    missing = {i for i in range(number + 1)} - set(state.keys())
    if missing:
      print(" ".join([str(i) for i in missing]))
    else:
      break

  res = "".join([state[i] for i in range(number + 1)])
  res = res.ljust(((len(res) + 7) // 8) * 8, '=')
  res = base64.b32decode(res)

  return base64.b16encode(res[:64]).decode(),zlib.decompress(res[64:])

def makepdf(output: str, picis: str):
  pdf = fpdf.FPDF()
  pdf.add_page()
  for i in range(len(picis)):
    pdf.image(picis[i], 5 + 100 * (i%2), 5 + 90 * (i//2), 90, 90)
  pdf.output(output)

def help():
  print(f"Usage: {sys.argv[0]} <mode> <args>...")
  print("")
  print("Modes:")
  print("compress <input> <output>")
  print("  Compresses the image in <input> to the gif file <output>,")
  print("  and outputs the hexadecimal hash")
  print("")
  print("keygen")
  print("  Securely generates a Ed25519 keypair, and prints the hexadecimal")
  print("  private and public keys in order, separated by a line break")
  print("")
  print("sign <hash> <privatekey>")
  print("  Signs the hexadecimal <hash> with the hexadecimal Ed25519 private")
  print("  key <privatekey>, and outputs the hexadecimal signature")
  print("")
  print("encode <image> <signature> <output>")
  print("  Creates QR codes in the directory <output> from the compressed")
  print("  gif in <image> and the Ed25519 hexadecimal signature <signature>.")
  print("  The optional [detail] parameter increases the version of the QR code")
  print("")
  print("decode <image> <qr codes>...")
  print("  Reads the QR codes and attempts to deserialise them into the")
  print("  image and signature respectively. If there are missing images,")
  print("  it prints their indexes delimited by spaces and returns 3,")
  print("  otherwise it prints the hexadecimal signature and returns 0.")
  print("  If it cannot find any QR codes, it will return 3 and output nothing.")
  print("")
  print("decodecam <image> [webcam]")
  print("  Reads the QR codes from [webcam] (if not specified, the default webcam),")
  print("  and follows the same process as decode, writing the new state on each line,")
  print("  and only exiting when all QR codes are read, or an error occurs")
  print("")
  print("check <image> <signature> <publickey>")
  print("  Checks if the data in <image> was signed with the hexadecimal signature <signature>")
  print("  by the hexadecimal Ed25519 public key <publickey>. Returns 2 if the check fails.")
  print("")
  print("makepdf <output> <images>...")
  print("  Makes a PDF from the QR codes in <images> and stores it in <output>")

def main():
  if len(sys.argv) < 2:
    help()
    return 1
  if sys.argv[1] == "compress":
    if len(sys.argv) != 4:
      print("Invalid compress command")
      help()
      return 1
    if not sys.argv[3].endswith(".bmp") and False:
      print("Output must have a .bmp file extension!")
      return 1
    compress_img(sys.argv[2], sys.argv[3])
    with open(sys.argv[3], "rb") as file:
      data = file.read()
    print(hashlib.sha256(data).hexdigest())
    return 0
  elif sys.argv[1] == "keygen":
    if len(sys.argv) != 2:
      print("Invalid keygen command")
      help()
      return 1
    priv, pub = keygen()
    print(priv)
    print(pub)
    return 0
  elif sys.argv[1] == "sign":
    if len(sys.argv) != 4:
      print("Invalid sign command")
      help()
      return 1
    print(sign(sys.argv[2], sys.argv[3]))
  elif sys.argv[1] == "encode":
    if len(sys.argv) != 5:
      print("Invalid encode command")
      help()
      return 1
    with open(sys.argv[2], "rb") as image_file:
      compressed = image_file.read()
    encode(compressed, sys.argv[3], sys.argv[4])
  elif sys.argv[1] == "decode":
    if len(sys.argv) < 4:
      print("Invalid decode command")
      help()
      return 1
    res = decode(sys.argv[3:])
    if type(res) == set:
      print(" ".join([str(i) for i in res]))
      return 3
    with open(sys.argv[2], "wb") as img_file:
      img_file.write(res[1])
    print(res[0])
  elif sys.argv[1] == "decodecam":
    if len(sys.argv) not in {3, 4}:
      print("Invalid decodecam command")
    sig, dat = decodecam(sys.argv[3]) if len(sys.argv) == 4 else decodecam()
    with open(sys.argv[2], "wb") as img_file:
      img_file.write(dat)
    print(sig)
  elif sys.argv[1] == "check":
    if len(sys.argv) != 5:
      print("Invalid check command")
      help()
      return 1
    with open(sys.argv[2], "rb") as file:
      data = file.read()
    hash = hashlib.sha256(data).hexdigest()
    if check(hash, sys.argv[3], sys.argv[4]):
      print("Signature valid")
      return 0
    else:
      print("Incorrect signature")
      return 2
  elif sys.argv[1] == "makepdf":
    if len(sys.argv) < 4:
      print("Invalid makepdf command")
      help()
      return 1
    makepdf(sys.argv[2], sys.argv[3:])
    return 0
  else:
    print("Unknown mode!")
    help()
    return 1
if __name__ == "__main__":
  sys.exit(main())

filename = sys.argv[1]
output_dir = sys.argv[2]

compressed = compress_img(filename)
chunks = chunk_data(compressed)
for i in range(len(chunks)):
  generate_qr(chunks[i]).save(f"{output_dir}/{i}.png")


