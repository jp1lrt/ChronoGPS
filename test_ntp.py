from ntp_client import NTPClient

def main():
    c = NTPClient()
    try:
        t, off_ms = c.get_time()
        print("OK:", t, "offset_ms=", off_ms)
    except Exception as e:
        print("EXCEPTION:", repr(e))
    input("Enterで終了...")

if __name__ == "__main__":
    main()
