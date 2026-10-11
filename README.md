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
- Keyboard drives the selected droid: Tab or F1-F4 picks which one. WASD/arrows drive, Shift boosts, Q/E change the top speed, 1-0 play emotes, P pats, O pokes, Z/C turn the dome, X changes stance (R2 droids only), Space stops, Esc disconnects.
- Controllers: pad 1 drives droid 1, pad 2 drives droid 2 and so on. Back/View changes which droid a pad drives. Left stick drives, RT boosts, LT slows, A/B/X/Y play emotes, LB pats, RB changes stance, Start plays a random emote, right stick turns the dome.

## Modes (pick one per droid with the buttons under its stats)
- **Drive**: free roam with keyboard or controller.
- **Patrol**: the droid wanders around by itself, backs away and turns when it bumps into something, and plays emotes now and then. "Patrol ALL" sends every droid out at once. Pressing any drive key or moving the stick stops it.
- **Path**: draw a line on the canvas and press **Go!**. The droid follows it, with "up" on the screen being the way the droid is facing. Distances are rough guesses based on time.
- **Record**: press Record, drive and play emotes, then press Stop. **Play** replays it and **Save** keeps it, so you can load it again later.

## Force Band
Click **Force Band** at the bottom left.
- **Real bands:** Sphero never published how the Force Band talks over Bluetooth, and nobody has documented it online. This app makes a best guess, using the same unlock code and messages as the droids and reading the band's motion sensor. It may not connect, or the gestures may not be detected properly. If it fails, check `log.txt`.
- **Demo band:** works for everything without a band. Do gestures with the keys I (push), K (pull), J (left), L (right), U (up) and M (stop), or with the on-screen buttons.
- **Control:** push drives forward, pull drives backward, left/right turn and go, stop stops, and up makes the droid cheer. It controls the droid that's selected.
- **Data Cubes:** a hunting game with 30 collectible cubes. Aim the scanner (with the band, or point the mouse with the Demo band) until the signal is strong and it locks on, then do a PULL to grab the cube. Your collection is saved in `data_cubes.json`.
- **Reflex** (do the gesture that's shown before time runs out) and **Duel** (block the training bot's attacks, then push to strike) are training games. They use simple made-up sounds.
- Holocrons you collected in the old official app were stored in your Sphero account, not on the band, so they can't be brought into this app.

## Updates
When a new version comes out, a green banner pops up at the top. Click **Update now**, then **Restart & update**. You can also click **Check for updates** in the Controls panel. Your droids' memories, recordings and Data Cubes are never touched.

## Personality
Each droid remembers its mood, energy, XP, level, bumps and pats, plus its friendships with your other droids. All of this is saved in `%APPDATA%\DroidCommander`. When droids are connected together they greet each other, chat when they're idle, show off tricks, and react when another droid crashes or goes fast. If something breaks, look in `%APPDATA%\DroidCommander\log.txt`.
