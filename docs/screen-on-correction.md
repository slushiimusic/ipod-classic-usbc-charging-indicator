# Screen-on charging edge correction, v0.3.0

The previous estimator reset its inactive voltage baseline whenever either
observed load bit changed. That discarded a real charging-voltage rise if it
arrived together with a backlight-off-to-on change.

Version 4 preserves the preceding baseline only for a fresh backlight-only
turn-on. The large-rise threshold (32 ADC counts), confirmation (400 clock
ticks), startup settling and freshness checks remain mandatory. Smaller
qualified reconnect pairs are still erased by any observed load transition.
Backlight turn-off and storage-load changes still rebase. Native 30-pin
charging still has priority. No charger or wake-source register is changed.

## Evidence and limits

The prior physical build detected 15 of 18 USB-C connections. One miss occurred
with the screen off, and USB-C did not wake the device. There is no trace tying
those misses to this specific code path. **This correction is locally checked,
not physically validated, and does not establish that all misses are fixed.**

The new source passed the existing 231 reconnect, ramp, tolerance and widget
cases. A further 19 tests on the combined menu/charging image cover fresh
screen-on rises, other load changes, small rises, spikes, stale readings and
two minutes of backlight-only voltage shifts. Accepted ideal abrupt rises
confirmed after 500–750 ms; those are simulated timings. See
[the screen-on cases](screen-on-validation.json).

USB-C wake from deep sleep remains unresolved. The estimator executes only
while the processor schedules it, and no usable kit USB-C wake signal has been
established. A polling gap invalidates the old voltage baseline. Flat high
voltage after waking cannot distinguish a connected charger from an unplugged
charged battery. The patch does not disable sleep or add periodic wakeups.

Load changes can still imitate charging. Small or absent voltage edges,
including near full charge, can still cause misses. This remains a display
estimate, not a measurement of cable presence or charging current. The
[kit manufacturer's troubleshooting page](https://moonlit.market/pages/troubleshooting-for-classic-connect-2)
also distinguishes USB-C charging from Apple's charging indicator.

The 250 ms polling period is unchanged from v3. CPU policy is unchanged.
Physical battery cost has not been measured.
