import wand.image,qrcode,sys,hashlib,base64
img = wand.image.Image(filename=sys.argv[1])
img.resize(200, 200)
img.quantize(8, "gray")
img.save(filename=sys.argv[2])
with open(sys.argv[2], "rb") as file:
  data = file.read()
  print(hashlib.sha256(data).hexdigest())
  data = base64.b32encode(base64.b16decode(input("Signature: ").upper()) + data).decode().rstrip('=')
  number = 6; chunks = [f'{i}{number}' + data[i * (len(data) // number): (i+1) * (len(data) // number)] for i in range(number)]
  for i in range(len(chunks)):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=20, border=4)
    qr.add_data(chunks[i])
    qr.make_image(fill_color="black", back_color="white").save(f"{sys.argv[3]}/{i}.png")
