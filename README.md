## MT7687 flasher tool

This tool is a replacement for the Windows-only MT7687 flasher tool from
Mediatek.

## Dependencies / Installation

    pip install -r requirements.txt

No setup.py for now, just run the script standalone.

You need the `bin` folder from the Windows flasher. Copy it next to
`mt7687flash.py` or pass its path with the `-b` option.

## Usage

See the built-in help:

    python mt7687flash.py --help

Example:

    python mt7687flash.py -p /dev/ttyACM1 -s hs \
        -w 0x0:mt7687_bootloader.bin \
        -w 0xb000:WIFI_RAM_CODE_MT76X7_in_flash.bin \
        -w 0x7c000:mt7687_iot_sdk_demo.bin

    Opening port at 115200 baud...
    Sending baudrate switcher (uart_hs.bin)...
      Sending... 100%
    Reopening port at 921600 baud...
    Sending ATED (ated_hs.bin)...
      Sending... 100%
    Flash size: 0x200000
    Writing to 0x0: mt7687_bootloader.bin
      Erasing... 100%
      Writing... 100%
    Writing to 0xb000: WIFI_RAM_CODE_MT76X7_in_flash.bin
      Erasing... 100%
      Writing... 100%
    Writing to 0x7c000: mt7687_iot_sdk_demo.bin
      Erasing... 100%
      Writing... 100%

## TODO

Implement readout
