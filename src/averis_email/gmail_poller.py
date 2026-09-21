"""Background Gmail ingestion.

The transport, MIME parser, and disk store stay independent; this module owns
only checkpointing and scheduling. A single cycle is deliberately exposed as
``run_once`` so all correctness rules can be tested without threads or sleeps.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread, current_thread

from averis_email import gmail_client, gmail_mime
from averis_email.gmail_client import GmailAuthError, GmailConnectionError


@dataclass(frozen=True)
class PollOutcome:
    status: str
    ingested: int = 0
    skipped: int = 0
    last_uid: int | None = None


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def run_once(settings, store):
    """Run one Gmail synchronization cycle and persist progress per UID.

    A newly enabled mailbox is baselined at its current tip; existing mail is
    not backfilled. Each later cycle ingests only higher UIDs. A malformed or
    oversized message is recorded as skipped and its UID is still checkpointed
    so one bad email cannot block the mailbox forever.
    """
    config = settings.get()
    if not config.get('enabled') or not config.get('address') or not config.get('password'):
        return PollOutcome('disabled', last_uid=config.get('last_uid'))

    address, password = config['address'], config['password']
    try:
        uidvalidity, uidnext = gmail_client.mailbox_status(address, password)
        if config.get('last_uid') is None or config.get('uidvalidity') != uidvalidity:
            baseline = max(0, uidnext - 1)
            settings.set_sync_state(expected_address=address, uidvalidity=uidvalidity, last_uid=baseline,
                                    last_poll_at=_stamp(), last_error=None)
            return PollOutcome('baselined', last_uid=baseline)

        fetched_uidvalidity, messages = gmail_client.fetch_since(
            address, password, int(config['last_uid']))
        if fetched_uidvalidity != uidvalidity:
            # The mailbox was recreated between STATUS and FETCH. Discard that
            # ambiguous fetch and establish a fresh tip on the new UID space.
            fresh_validity, fresh_next = gmail_client.mailbox_status(address, password)
            baseline = max(0, fresh_next - 1)
            settings.set_sync_state(expected_address=address, uidvalidity=fresh_validity, last_uid=baseline,
                                    last_poll_at=_stamp(), last_error=None)
            return PollOutcome('baselined', last_uid=baseline)

        ingested = 0
        skipped = 0
        last_uid = int(config['last_uid'])
        total = int(config.get('ingested_count') or 0)
        warnings = []
        for uid, raw, reason in sorted(messages, key=lambda item: item[0]):
            if raw is None:
                skipped += 1
                warnings.append(f'UID {uid}: {reason or "message was skipped"}')
            else:
                try:
                    record, attachments = gmail_mime.parse_message(raw, uid, uidvalidity)
                except Exception as exc:  # malformed mail must not wedge the inbox
                    skipped += 1
                    warnings.append(f'UID {uid}: {type(exc).__name__}: {exc}')
                else:
                    # Storage failures deliberately propagate before checkpointing,
                    # so the UID is retried instead of silently losing a message.
                    was_new = not store.exists(record['email_id'])
                    store.ingest(record, attachments)
                    if was_new:
                        ingested += 1
                        total += 1
            last_uid = uid
            settings.set_sync_state(expected_address=address, uidvalidity=uidvalidity, last_uid=uid,
                                    ingested_count=total,
                                    last_error='; '.join(warnings[-3:]) or None)

        settings.set_sync_state(expected_address=address, uidvalidity=uidvalidity, last_uid=last_uid,
                                ingested_count=total, last_poll_at=_stamp(),
                                last_error='; '.join(warnings[-3:]) or None)
        return PollOutcome('ok', ingested=ingested, skipped=skipped, last_uid=last_uid)
    except (GmailAuthError, GmailConnectionError) as exc:
        settings.set_sync_state(expected_address=address, last_poll_at=_stamp(), last_error=str(exc))
        raise


class GmailPoller:
    """Single daemon loop with immediate shutdown and bounded backoff."""

    def __init__(self, settings, store, interval=60, on_change=None):
        self.settings = settings
        self.store = store
        self.interval = max(1, int(interval))
        self.on_change = on_change
        self._stop = Event()
        self._thread = None
        self._guard = Lock()

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        with self._guard:
            if self.running:
                return False
            self._stop = Event()
            self._thread = Thread(target=self._loop, name='gmail-poller', daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout=5):
        with self._guard:
            thread = self._thread
            self._stop.set()
        if thread and thread is not current_thread():
            thread.join(timeout)
        return not self.running

    def _loop(self):
        auth_failures = 0
        network_failures = 0
        delay = 0
        while not self._stop.wait(delay):
            try:
                outcome = run_once(self.settings, self.store)
                auth_failures = network_failures = 0
                delay = self.interval
                if self.on_change and (outcome.ingested or outcome.skipped or outcome.status == 'baselined'):
                    self.on_change(outcome)
            except GmailAuthError:
                auth_failures += 1
                network_failures = 0
                delay = 60 if auth_failures == 1 else 3600
            except GmailConnectionError:
                network_failures += 1
                auth_failures = 0
                delay = 60 if network_failures == 1 else 300
            except Exception as exc:
                # Preserve the thread for unexpected parser/disk failures and
                # expose the problem through the same status field.
                self.settings.set_sync_state(last_poll_at=_stamp(),
                                             last_error=f'{type(exc).__name__}: {exc}')
                delay = 300
