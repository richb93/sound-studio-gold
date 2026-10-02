"""MIDI ports via mido + python-rtmidi.  Without them the program still runs, silently."""
import threading

try:
    import mido
except Exception:          # pragma: no cover - optional dependency
    mido = None


def available():
    return mido is not None


def output_names():
    if not mido:
        return []
    try:
        return list(dict.fromkeys(mido.get_output_names()))
    except Exception:
        return []


def input_names():
    if not mido:
        return []
    try:
        return list(dict.fromkeys(mido.get_input_names()))
    except Exception:
        return []


class MidiIO:
    """Holds the opened output ports (indexed like Gold's 'A:', 'B:' ... port letters) and inputs."""

    def __init__(self):
        self.outs = []          # list of (name, port or None)
        self.ins = []
        self.lock = threading.Lock()
        self.on_input = None    # callback(bytes)

    # ---- outputs
    def open_outputs(self, names):
        self.close_outputs()
        for nm in names:
            port = None
            if mido:
                try:
                    port = mido.open_output(nm)
                except Exception:
                    port = None
            self.outs.append((nm, port))

    def close_outputs(self):
        for _nm, p in self.outs:
            try:
                if p:
                    p.close()
            except Exception:
                pass
        self.outs = []

    def port_labels(self):
        """'A: name' labels as shown by Gold's port selectors."""
        return ['%s: %s' % (chr(65 + i), nm) for i, (nm, _p) in enumerate(self.outs)] or ['A: (no MIDI output)']

    def real_port(self, port):
        """The output a port number plays on: songs may name ports this computer doesn't have,
        and those play on the first one."""
        return port if 0 <= port < len(self.outs) else 0

    def send(self, port, data):
        if not self.outs:
            return
        port = self.real_port(port)
        p = self.outs[port][1]
        if p is None:
            return
        try:
            msg = mido.Message.from_bytes(list(data))
        except Exception:
            return
        with self.lock:
            try:
                p.send(msg)
            except Exception:
                pass

    def send_all(self, data):
        for i in range(len(self.outs)):
            self.send(i, data)

    def all_notes_off(self):
        for i in range(len(self.outs)):
            for ch in range(16):
                self.send(i, bytes([0xB0 | ch, 123, 0]))
                self.send(i, bytes([0xB0 | ch, 64, 0]))

    # ---- inputs
    def open_inputs(self, names):
        self.close_inputs()
        for nm in names:
            port = None
            if mido:
                try:
                    port = mido.open_input(nm, callback=self._recv)
                except Exception:
                    port = None
            self.ins.append((nm, port))

    def close_inputs(self):
        for _nm, p in self.ins:
            try:
                if p:
                    p.close()
            except Exception:
                pass
        self.ins = []

    def _recv(self, msg):
        cb = self.on_input
        if cb and msg.type not in ('clock', 'active_sensing'):
            try:
                cb(bytes(msg.bytes()))
            except Exception:
                pass

    def close(self):
        self.close_outputs()
        self.close_inputs()
