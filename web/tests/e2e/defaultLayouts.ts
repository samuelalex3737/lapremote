// Generated from agent/lapremote/layouts.py default_layouts("windows"). Do not edit by hand.
export const DEFAULT_LAYOUTS = [
  {
    "id": "zoom",
    "name": "Zoom call",
    "match": {
      "processes": [
        "zoom.exe",
        "zoom.us",
        "zoom"
      ],
      "sites": [],
      "titles": [
        "Zoom Meeting"
      ]
    },
    "buttons": [
      {
        "label": "Mute",
        "icon": "mic",
        "action": {
          "type": "key",
          "key": "a",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Camera",
        "icon": "video",
        "action": {
          "type": "key",
          "key": "v",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Share screen",
        "icon": "screen-share",
        "action": {
          "type": "key",
          "key": "s",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Raise hand",
        "icon": "hand",
        "action": {
          "type": "key",
          "key": "y",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Chat",
        "icon": "message",
        "action": {
          "type": "key",
          "key": "h",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Leave",
        "icon": "phone-off",
        "action": {
          "type": "key",
          "key": "q",
          "modifiers": [
            "alt"
          ]
        }
      }
    ]
  },
  {
    "id": "teams",
    "name": "Teams call",
    "match": {
      "processes": [
        "ms-teams.exe",
        "teams.exe",
        "microsoft teams"
      ],
      "sites": [],
      "titles": [
        "Microsoft Teams"
      ]
    },
    "buttons": [
      {
        "label": "Mute",
        "icon": "mic",
        "action": {
          "type": "key",
          "key": "m",
          "modifiers": [
            "ctrl",
            "shift"
          ]
        }
      },
      {
        "label": "Camera",
        "icon": "video",
        "action": {
          "type": "key",
          "key": "o",
          "modifiers": [
            "ctrl",
            "shift"
          ]
        }
      },
      {
        "label": "Share screen",
        "icon": "screen-share",
        "action": {
          "type": "key",
          "key": "e",
          "modifiers": [
            "ctrl",
            "shift"
          ]
        }
      },
      {
        "label": "Raise hand",
        "icon": "hand",
        "action": {
          "type": "key",
          "key": "k",
          "modifiers": [
            "ctrl",
            "shift"
          ]
        }
      },
      {
        "label": "Leave",
        "icon": "phone-off",
        "action": {
          "type": "key",
          "key": "h",
          "modifiers": [
            "ctrl",
            "shift"
          ]
        }
      }
    ]
  },
  {
    "id": "meet",
    "name": "Google Meet",
    "match": {
      "processes": [],
      "sites": [],
      "titles": [
        "Meet - ",
        "Google Meet"
      ]
    },
    "buttons": [
      {
        "label": "Mute",
        "icon": "mic",
        "action": {
          "type": "key",
          "key": "d",
          "modifiers": [
            "ctrl"
          ]
        }
      },
      {
        "label": "Camera",
        "icon": "video",
        "action": {
          "type": "key",
          "key": "e",
          "modifiers": [
            "ctrl"
          ]
        }
      },
      {
        "label": "Raise hand",
        "icon": "hand",
        "action": {
          "type": "key",
          "key": "h",
          "modifiers": [
            "ctrl",
            "alt"
          ]
        }
      },
      {
        "label": "Chat",
        "icon": "message",
        "action": {
          "type": "key",
          "key": "c",
          "modifiers": [
            "ctrl",
            "alt"
          ]
        }
      },
      {
        "label": "Leave (closes tab)",
        "icon": "phone-off",
        "action": {
          "type": "key",
          "key": "w",
          "modifiers": [
            "ctrl"
          ]
        }
      }
    ]
  },
  {
    "id": "vlc",
    "name": "VLC",
    "match": {
      "processes": [
        "vlc.exe",
        "vlc"
      ],
      "sites": [],
      "titles": []
    },
    "buttons": [
      {
        "label": "Play / pause",
        "icon": "play",
        "action": {
          "type": "key",
          "key": "space",
          "modifiers": []
        }
      },
      {
        "label": "Back 10s",
        "icon": "rewind",
        "action": {
          "type": "key",
          "key": "left",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Forward 10s",
        "icon": "fast-forward",
        "action": {
          "type": "key",
          "key": "right",
          "modifiers": [
            "alt"
          ]
        }
      },
      {
        "label": "Fullscreen",
        "icon": "maximize",
        "action": {
          "type": "key",
          "key": "f",
          "modifiers": []
        }
      },
      {
        "label": "Subtitles",
        "icon": "captions",
        "action": {
          "type": "key",
          "key": "v",
          "modifiers": []
        }
      },
      {
        "label": "Mute",
        "icon": "volume-x",
        "action": {
          "type": "key",
          "key": "m",
          "modifiers": []
        }
      },
      {
        "label": "Volume up",
        "icon": "volume-2",
        "action": {
          "type": "key",
          "key": "up",
          "modifiers": [
            "ctrl"
          ]
        }
      },
      {
        "label": "Volume down",
        "icon": "volume-1",
        "action": {
          "type": "key",
          "key": "down",
          "modifiers": [
            "ctrl"
          ]
        }
      }
    ]
  },
  {
    "id": "spotify",
    "name": "Spotify",
    "match": {
      "processes": [
        "spotify.exe",
        "spotify"
      ],
      "sites": [
        "spotify_web"
      ],
      "titles": []
    },
    "buttons": [
      {
        "label": "Play / pause",
        "icon": "play",
        "action": {
          "type": "media",
          "command": "toggle"
        }
      },
      {
        "label": "Previous",
        "icon": "skip-back",
        "action": {
          "type": "media",
          "command": "prev"
        }
      },
      {
        "label": "Next",
        "icon": "skip-forward",
        "action": {
          "type": "media",
          "command": "next"
        }
      },
      {
        "label": "Shuffle",
        "icon": "shuffle",
        "action": {
          "type": "key",
          "key": "s",
          "modifiers": [
            "ctrl"
          ]
        }
      },
      {
        "label": "Repeat",
        "icon": "repeat",
        "action": {
          "type": "key",
          "key": "r",
          "modifiers": [
            "ctrl"
          ]
        }
      },
      {
        "label": "Volume up",
        "icon": "volume-2",
        "action": {
          "type": "key",
          "key": "up",
          "modifiers": [
            "ctrl"
          ]
        }
      },
      {
        "label": "Volume down",
        "icon": "volume-1",
        "action": {
          "type": "key",
          "key": "down",
          "modifiers": [
            "ctrl"
          ]
        }
      }
    ]
  },
  {
    "id": "youtube",
    "name": "YouTube",
    "match": {
      "processes": [],
      "sites": [
        "youtube"
      ],
      "titles": []
    },
    "buttons": [
      {
        "label": "Play / pause",
        "icon": "play",
        "action": {
          "type": "key",
          "key": "k",
          "modifiers": []
        }
      },
      {
        "label": "Back 10s",
        "icon": "rewind",
        "action": {
          "type": "key",
          "key": "j",
          "modifiers": []
        }
      },
      {
        "label": "Forward 10s",
        "icon": "fast-forward",
        "action": {
          "type": "key",
          "key": "l",
          "modifiers": []
        }
      },
      {
        "label": "Fullscreen",
        "icon": "maximize",
        "action": {
          "type": "key",
          "key": "f",
          "modifiers": []
        }
      },
      {
        "label": "Captions",
        "icon": "captions",
        "action": {
          "type": "key",
          "key": "c",
          "modifiers": []
        }
      },
      {
        "label": "Mute",
        "icon": "volume-x",
        "action": {
          "type": "key",
          "key": "m",
          "modifiers": []
        }
      },
      {
        "label": "Next video",
        "icon": "skip-forward",
        "action": {
          "type": "key",
          "key": "n",
          "modifiers": [
            "shift"
          ]
        }
      },
      {
        "label": "Theater",
        "icon": "rectangle-horizontal",
        "action": {
          "type": "key",
          "key": "t",
          "modifiers": []
        }
      }
    ]
  }
]
