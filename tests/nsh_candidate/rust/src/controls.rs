use nsh_core::clipboard::{ClipboardBackend, MemoryClipboard};
use std::sync::{Condvar, Mutex};

#[derive(Default)]
pub(crate) struct DeliveryGate {
    state: Mutex<(bool, bool)>,
    changed: Condvar,
}

impl DeliveryGate {
    pub fn pause(&self) {
        let mut state = self.state.lock().unwrap();
        state.0 = true;
        self.changed.notify_all();
        while !state.1 {
            state = self.changed.wait(state).unwrap();
        }
    }

    pub fn wait_entered(&self) -> Result<(), String> {
        let mut state = self.state.lock().unwrap();
        while !state.0 && !state.1 {
            state = self.changed.wait(state).unwrap();
        }
        if state.0 {
            Ok(())
        } else {
            Err("BARRIER_RELEASED".into())
        }
    }

    pub fn release(&self) {
        self.state.lock().unwrap().1 = true;
        self.changed.notify_all();
    }

    pub fn released(&self) -> bool {
        self.state.lock().unwrap().1
    }
}

#[derive(Default)]
pub(crate) struct ClipboardPolicy {
    backend: MemoryClipboard,
    version: u32,
    owned: Option<(u32, u64)>,
    now: u64,
}

impl ClipboardPolicy {
    fn next_version(&mut self) -> u32 {
        self.version = self
            .version
            .checked_add(1)
            .expect("synthetic clipboard version exhausted");
        self.version
    }

    pub fn copy(&mut self, text: String) -> u32 {
        let version = self.next_version();
        self.backend.set_text(Some(text));
        self.owned = Some((version, self.now + 1000));
        version
    }

    pub fn external_copy(&mut self, same: bool) {
        let text = if same {
            self.backend.text().unwrap_or_default()
        } else {
            "synthetic-external".into()
        };
        self.next_version();
        self.owned = None;
        self.backend.set_text(Some(text));
    }

    pub fn expire(&mut self, version: u32) {
        if self
            .owned
            .is_some_and(|(owner, deadline)| owner == version && self.now >= deadline)
        {
            self.clear_owned();
        }
    }

    pub fn advance(&mut self, milliseconds: u32) -> Result<(), String> {
        if milliseconds > 60000 {
            return Err("INVALID_CLOCK".into());
        }
        self.now = self
            .now
            .checked_add(milliseconds as u64)
            .ok_or("INVALID_CLOCK")?;
        self.expire(self.version);
        Ok(())
    }

    pub fn clear_owned(&mut self) {
        if self.owned.take().is_some() {
            self.backend.set_text(None);
            self.next_version();
        }
    }

    pub fn status(&self) -> String {
        if self.backend.text().is_none() {
            "empty"
        } else if self.owned.is_some() {
            "owned"
        } else {
            "external"
        }
        .into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clipboard_versions_expiry_external_same_value_and_empty_lock() {
        let mut clipboard = ClipboardPolicy::default();
        clipboard.clear_owned();
        assert_eq!(clipboard.status(), "empty");
        let first = clipboard.copy("synthetic-secret".into());
        clipboard.advance(600).unwrap();
        clipboard.copy("synthetic-secret".into());
        clipboard.advance(400).unwrap();
        clipboard.expire(first);
        assert_eq!(clipboard.status(), "owned");
        clipboard.advance(600).unwrap();
        assert_eq!(clipboard.status(), "empty");
        clipboard.copy("synthetic-secret".into());
        clipboard.external_copy(true);
        clipboard.clear_owned();
        clipboard.advance(1000).unwrap();
        assert_eq!(
            clipboard.backend.text().as_deref(),
            Some("synthetic-secret")
        );
        assert_eq!(clipboard.status(), "external");
        clipboard.copy("synthetic-secret".into());
        clipboard.clear_owned();
        assert_eq!(clipboard.status(), "empty");
        assert!(clipboard.advance(60001).is_err());
    }

    #[test]
    fn gate_releases_on_command_and_cancelled_wait_is_an_error() {
        let gate = std::sync::Arc::new(DeliveryGate::default());
        let worker = gate.clone();
        let thread = std::thread::spawn(move || worker.pause());
        gate.wait_entered().unwrap();
        assert!(!gate.released());
        gate.release();
        thread.join().unwrap();
        let unused = DeliveryGate::default();
        unused.release();
        assert!(unused.wait_entered().is_err());
    }
}
