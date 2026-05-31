from instagrapi import Client
cl = Client()
try:
    cl.login("fpvlouis", "20WestAvenue1!")
    print("LOGIN OK")
except Exception as e:
    print(f"ERROR: {e}")
