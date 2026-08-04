from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.party_lore.models import LoreEntry, LoreUsage
from app.modules.party_lore.schemas import LoreCandidateCreate, LoreRetrieve
from app.modules.party_lore.service import (
    create_candidate,
    delete_entry,
    list_candidates,
    list_entries,
    retrieve_entries,
    review_candidate,
)
from app.platform.models import OutboxEvent


class PartyLoreTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(username="lore-owner", email="lore-owner@test", hashed_password="x")
        self.friend = User(username="lore-friend", email="lore-friend@test", hashed_password="x")
        self.member = User(username="lore-member", email="lore-member@test", hashed_password="x")
        self.outsider = User(username="lore-outsider", email="lore-outsider@test", hashed_password="x")
        self.db.add_all([self.owner, self.friend, self.member, self.outsider])
        self.db.flush()
        self.server = Server(name="Lore Server", owner_id=self.owner.id)
        self.db.add(self.server)
        self.db.flush()
        self.db.add_all(
            [
                ServerMember(user_id=self.owner.id, server_id=self.server.id),
                ServerMember(user_id=self.friend.id, server_id=self.server.id),
                ServerMember(user_id=self.member.id, server_id=self.server.id),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def payload(self, *, sensitivity: str = "low") -> LoreCandidateCreate:
        return LoreCandidateCreate(
            title="The impossible comeback",
            summary="Owner and friend won after everyone thought the round was over.",
            participant_ids=[self.owner.id, self.friend.id],
            category="comeback",
            sensitivity=sensitivity,
            allowed_modules=["ai_commentator", "meme_generator"],
        )

    def create(self, *, key: str = "lore-create-001", sensitivity: str = "low"):
        return create_candidate(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=self.payload(sensitivity=sensitivity),
            idempotency_key=key,
        )

    def confirm(self, candidate):
        review_candidate(
            self.db,
            candidate_id=candidate.id,
            actor=self.owner,
            decision="approved",
        )
        return review_candidate(
            self.db,
            candidate_id=candidate.id,
            actor=self.friend,
            decision="approved",
        )

    def test_candidate_is_idempotent_and_requires_every_participant(self):
        candidate = self.create()
        repeated = self.create()
        self.assertEqual(candidate.id, repeated.id)

        candidate = review_candidate(
            self.db,
            candidate_id=candidate.id,
            actor=self.owner,
            decision="approved",
        )
        self.assertEqual(candidate.status, "pending")
        self.assertEqual(self.db.query(LoreEntry).count(), 0)

        candidate = review_candidate(
            self.db,
            candidate_id=candidate.id,
            actor=self.friend,
            decision="approved",
        )
        self.assertEqual(candidate.status, "confirmed")
        self.assertIsNotNone(candidate.entry)
        self.assertEqual(self.db.query(LoreEntry).count(), 1)
        self.assertEqual(
            {participant.user_id for participant in candidate.entry.participants},
            {self.owner.id, self.friend.id},
        )
        self.assertEqual(self.db.query(OutboxEvent).count(), 3)

    def test_rejection_is_terminal_and_non_participant_cannot_review(self):
        candidate = self.create()
        with self.assertRaises(HTTPException) as forbidden:
            review_candidate(
                self.db,
                candidate_id=candidate.id,
                actor=self.member,
                decision="approved",
            )
        self.assertEqual(forbidden.exception.status_code, 403)

        candidate = review_candidate(
            self.db,
            candidate_id=candidate.id,
            actor=self.friend,
            decision="rejected",
        )
        self.assertEqual(candidate.status, "rejected")
        candidate = review_candidate(
            self.db,
            candidate_id=candidate.id,
            actor=self.owner,
            decision="approved",
        )
        self.assertEqual(candidate.status, "rejected")
        self.assertEqual(self.db.query(LoreEntry).count(), 0)

    def test_candidate_visibility_and_server_membership_are_enforced(self):
        candidate = self.create()
        self.assertEqual(
            [item.id for item in list_candidates(self.db, server_id=self.server.id, actor=self.friend)],
            [candidate.id],
        )
        self.assertEqual(
            list_candidates(self.db, server_id=self.server.id, actor=self.member),
            [],
        )
        with self.assertRaises(HTTPException) as forbidden:
            create_candidate(
                self.db,
                server_id=self.server.id,
                actor=self.outsider,
                payload=self.payload(),
                idempotency_key="outsider-lore-001",
            )
        self.assertEqual(forbidden.exception.status_code, 403)

    def test_retrieval_filters_usage_and_soft_delete_are_safe(self):
        candidate = self.confirm(self.create())
        entry = candidate.entry
        request = LoreRetrieve(
            request_id="commentary-round-001",
            module="ai_commentator",
            query="impossible comeback",
            participant_ids=[self.owner.id],
            limit=5,
        )
        first = retrieve_entries(self.db, server_id=self.server.id, actor=self.member, payload=request)
        second = retrieve_entries(self.db, server_id=self.server.id, actor=self.member, payload=request)
        self.assertEqual([item.id for item in first], [entry.id])
        self.assertEqual([item.id for item in second], [entry.id])
        self.assertEqual(self.db.query(LoreUsage).count(), 1)

        with self.assertRaises(HTTPException) as forbidden:
            delete_entry(self.db, lore_id=entry.id, actor=self.member)
        self.assertEqual(forbidden.exception.status_code, 403)
        delete_entry(self.db, lore_id=entry.id, actor=self.friend)
        self.assertEqual(
            retrieve_entries(self.db, server_id=self.server.id, actor=self.member, payload=request),
            [],
        )

    def test_high_sensitivity_is_only_listed_to_participants_and_never_auto_retrieved(self):
        candidate = self.confirm(self.create(key="lore-high-001", sensitivity="high"))
        entry = candidate.entry
        self.assertEqual(
            [item.id for item in list_entries(self.db, server_id=self.server.id, actor=self.owner)],
            [entry.id],
        )
        self.assertEqual(list_entries(self.db, server_id=self.server.id, actor=self.member), [])
        request = LoreRetrieve(
            request_id="high-sensitive-001",
            module="ai_commentator",
            query="",
        )
        self.assertEqual(
            retrieve_entries(self.db, server_id=self.server.id, actor=self.owner, payload=request),
            [],
        )


if __name__ == "__main__":
    unittest.main()
