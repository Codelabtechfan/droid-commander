# Droid Commander

Unofficial fan app to drive and play with Sphero app-enabled droids: BB-8, BB-9E, R2-D2 and R2-Q5.
Not made by or connected to Sphero, Disney or Lucasfilm. It uses no movie logos, fonts or sounds.

## How to use (Windows 11)
1. Turn on Bluetooth: Settings > Bluetooth & devices > Bluetooth **On**. Don't pair the droid in Windows; the app connects by itself.
2. Take your droid(s) off the charger and wake them up (pick up / shake). Keep them close to the PC.
3. Close the old Sphero app on any phone, otherwise the droid stays connected to the phone.
4. Double-click `DroidCommander.exe`. If Windows SmartScreen pops up, click **More info > Run anyway**.
5. Press **SCAN**, then click each droid to connect (up to 4 at once). **+ Demo droid** lets you try it with no droids.

## Controls
Click **Keybinds** (right panel) to change any key or controller button. Click a box, then press the new key or button (Esc cancels). **Reset defaults** puts the defaults back, and red text means two actions share a key. Your keybinds are saved in `%APPDATA%\DroidCommander\keybinds.json`.

- Keyboard drives the selected droid: Tab or F1-F4 picks which one. WASD/arrows drive, Shift boosts, Q/E change the top speed, 1-0 play emotes, P pats, O pokes, Z/C turn the dome, X changes stance (R2 droids only), Space stops, Esc disconnects.
- Controllers: pad 1 drives droid 1, pad 2 drives droid 2 and so on. Back/View changes which droid a pad drives. Left stick drives, RT boosts, LT slows, A/B/X/Y play emotes, LB pats, RB changes stance, Start plays a random emote, right stick turns the dome.

## Display
The **Display** button in the right panel switches between Windowed (you can resize it), Full window and Fullscreen. F11 also toggles fullscreen, and you can change that key in Keybinds. The app remembers your choice.

## Deep Sleep
The **Deep Sleep** button (next to Disconnect) makes the droid say goodnight, saves its memory and switches it fully off. To wake it up again, put it on its charger. You can give it a key in Keybinds; it has none by default.

## Modes (same as the original droid app, minus the movie and AR modes)
- **Drive**: drag the drive pad with the mouse, or use the keyboard or a controller. Hold **Boost** to go faster and **Reverse** to back up. There are 9 expression buttons, and R2-D2 and R2-Q5 also get a dome slider and a stance button. **Aim** turns the droid on the spot with its back light on; turn it until the light faces you, then press Done.
- **Patrol**: the droid roams around by itself, turns away when it hits something, and shows how far it has travelled. "Patrol ALL" sends every droid out.
- **Draw & Drive**: draw a path and the droid follows it.

## Force Band
Click **Force Band** at the bottom left.
- **Real bands:** Sphero never published how the Force Band talks over Bluetooth, and nobody has documented it online. This app makes a best guess, using the same unlock code and messages as the droids and reading the band's motion sensor. It may not connect, or the gestures may not be detected properly. If it fails, check `log.txt`.
- **Demo band:** works for everything without a band. Do gestures with the keys I (push), K (pull), J (left), L (right), U (up) and M (stop), or with the on-screen buttons.
- **Control:** push drives forward, pull drives backward, left/right turn and go, stop stops, and up makes the droid cheer. It controls the droid that's selected.
- **Data Cubes:** a hunting game with 30 collectible cubes. Aim the scanner (with the band, or point the mouse with the Demo band) until the signal is strong and it locks on, then do a PULL to grab the cube. Your collection is saved in `data_cubes.json`.
- **Reflex** (do the gesture that's shown before time runs out) and **Duel** (block the training bot's attacks, then push to strike) are training games. They use simple made-up sounds.
- Holocrons you collected in the old official app were stored in your Sphero account, not on the band, so they can't be brought into this app.

## Problems?
Click **Debug log** in the right panel to see what the app is doing. **Open folder** opens `%APPDATA%\DroidCommander`; send `log.txt` from there if something isn't working.

If the app ever crashes, the details are saved in `%APPDATA%\DroidCommander\crash.txt`.

## Updates
If an update ever fails, the app tells you next time it starts. The new version is then saved next to the old one as `DroidCommander-new.exe`, so you can run that instead.

When a new version comes out, a green banner pops up at the top. Click **Update now**, then **Restart & update**. You can also click **Check for updates** in the Controls panel. Your droids' memories, recordings and Data Cubes are never touched.

## Droid settings
The **Set** button on each droid in the list has these options:
- **Human interactions:** greetings and reactions to being driven fast, patted or bumped.
- **On-board idle animations:** the droid's own built-in idle moves. This works on BB-9E, R2-D2 and R2-Q5, but not on BB-8. The setting is sent to the droid every time it connects.
- **All interactions OFF/ON:** switches all of them off or back on at once.

## Memory
Each droid's settings are saved in `%APPDATA%\DroidCommander`.
