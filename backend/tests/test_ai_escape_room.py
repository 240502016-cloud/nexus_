from __future__ import annotations
import json,unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.models import Server,ServerMember,User
from app.database import Base
from app.modules.ai_escape_room.content import CONTENT_SETS,PRIVATE_CLUES,validate_graph
from app.modules.ai_escape_room.models import EscapePrivateConsole,EscapeRoomState,EscapeSimultaneousSubmission
from app.modules.ai_escape_room.schemas import EscapeCreate
from app.modules.ai_escape_room.service import create_room,room_view,submit_answer
from app.modules.ai_escape_room.worker import process_escape_host_job
from app.platform.models import AiRun,ExperienceEvent
from app.platform.worker import process_one as process_platform_one

class AiEscapeRoomTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite+pysqlite:///:memory:");Base.metadata.create_all(self.engine);self.Session=sessionmaker(bind=self.engine);self.db=self.Session()
        self.players=[User(username=f"escape-{i}",email=f"escape-{i}@test",hashed_password="x") for i in range(3)];self.out=User(username="escape-out",email="escape-out@test",hashed_password="x");self.db.add_all([*self.players,self.out]);self.db.flush()
        self.server=Server(name="NADIR",owner_id=self.players[0].id);self.db.add(self.server);self.db.flush();self.db.add_all([ServerMember(server_id=self.server.id,user_id=u.id) for u in self.players]);self.db.commit()
        self.session=create_room(self.db,server_id=self.server.id,actor=self.players[0],payload=EscapeCreate(player_ids=[u.id for u in self.players]),idempotency_key="escape-room-001")
    def tearDown(self):self.db.close();self.engine.dispose()
    def _solve(self,node_id,user,answer):
        view=room_view(self.db,session_id=self.session.id,actor=user);node=next(n for n in view["nodes"] if n["id"]==node_id)
        response=submit_answer(self.db,session_id=self.session.id,node_id=node_id,actor=user,answer=answer,token=node["submit_token"],revision=view["revision"],idempotency_key=f"solve-{node_id}-{user.id}");self.assertEqual(response["validator_result"],"CORRECT");return response["view"]
    def test_graph_private_consoles_and_duplicate_attempt(self):
        for content in CONTENT_SETS.values(): validate_graph(content["puzzles"],content["roles"])
        first=room_view(self.db,session_id=self.session.id,actor=self.players[0]);second=room_view(self.db,session_id=self.session.id,actor=self.players[1]);self.assertNotEqual(first["own_private"]["role"],second["own_private"]["role"])
        blob=self.db.query(EscapePrivateConsole).filter_by(user_id=self.players[0].id).one().encrypted_payload;self.assertNotIn(PRIVATE_CLUES["ENGINEER"]["E0"].encode(),blob)
        node=next(n for n in first["nodes"] if n["id"]=="E0");wrong=submit_answer(self.db,session_id=self.session.id,node_id="E0",actor=self.players[0],answer="000",token=node["submit_token"],revision=first["revision"],idempotency_key="wrong-001");revision=wrong["view"]["revision"]
        refreshed=wrong["view"];node=next(n for n in refreshed["nodes"] if n["id"]=="E0");duplicate=submit_answer(self.db,session_id=self.session.id,node_id="E0",actor=self.players[0],answer="000",token=node["submit_token"],revision=revision,idempotency_key="wrong-002");self.assertEqual(duplicate["validator_result"],"DUPLICATE");self.assertEqual(duplicate["view"]["revision"],revision)
        with self.assertRaises(HTTPException):room_view(self.db,session_id=self.session.id,actor=self.out)
    def test_complete_required_graph_with_three_private_meta_inputs(self):
        self._solve("E0",self.players[0],"317");self._solve("P1",self.players[0],"A-C-F");self._solve("P2",self.players[1],"DELTA,BETA,ALFA,GAMA");self._solve("P3",self.players[2],"K4");self._solve("G1",self.players[0],"471");self._solve("G2",self.players[1],"SOL-SAG-SOL");self._solve("O1",self.players[2],"NADIR")
        self._solve("M1",self.players[0],"ION");self._solve("M1",self.players[1],"47");view=self._solve("M1",self.players[2],"K4");self.assertEqual(next(n for n in view["nodes"] if n["id"]=="M1")["status"],"SOLVED");self.assertEqual(self.db.query(EscapeSimultaneousSubmission).count(),3)
        final=self._solve("F1",self.players[0],"ANAHTAR-MUHUR-UCUS");self.assertEqual(final["status"],"COMPLETED");self.assertEqual(final["result"]["grade"],"A");self.assertEqual(self.db.query(EscapeRoomState).filter_by(is_current=True).count(),1)
    def test_ai_host_only_narrates_committed_event(self):
        def fake_chat(*_args,**_kwargs):return {"model":"test","message":{"content":json.dumps({"message":"NADİR-3 kontrol odası çevrimiçi; üç konsol senkron bekliyor."},ensure_ascii=False)}}
        handler=lambda job_id:process_escape_host_job(job_id,chat=fake_chat)
        with patch("app.platform.worker.SessionLocal",self.Session),patch("app.modules.ai_escape_room.worker.SessionLocal",self.Session):self.assertTrue(process_platform_one(handlers={("ai_escape_room","escape.host_message"):handler}))
        self.assertEqual(self.db.query(AiRun).count(),1);self.assertEqual(self.db.query(ExperienceEvent).filter_by(event_type="escape.host_message_ready").count(),1)
class EscapeRoomTwoSeatTests(unittest.TestCase):
    """AI'sız iki kişilik oda: iki rollü bulmaca seti (nadir2-v1)."""
    def setUp(self):
        self.engine=create_engine("sqlite+pysqlite:///:memory:");Base.metadata.create_all(self.engine);self.Session=sessionmaker(bind=self.engine);self.db=self.Session()
        self.players=[User(username=f"duo-escape-{i}",email=f"duo-escape-{i}@test",hashed_password="x") for i in range(2)];self.db.add_all(self.players);self.db.flush()
        self.server=Server(name="NADIR duo",owner_id=self.players[0].id);self.db.add(self.server);self.db.flush();self.db.add_all([ServerMember(server_id=self.server.id,user_id=u.id) for u in self.players]);self.db.commit()
        self.session=create_room(self.db,server_id=self.server.id,actor=self.players[0],payload=EscapeCreate(player_ids=[u.id for u in self.players]),idempotency_key="duo-escape-001")
    def tearDown(self):self.db.close();self.engine.dispose()
    def _solve(self,node_id,user,answer):
        view=room_view(self.db,session_id=self.session.id,actor=user);node=next(n for n in view["nodes"] if n["id"]==node_id)
        response=submit_answer(self.db,session_id=self.session.id,node_id=node_id,actor=user,answer=answer,token=node["submit_token"],revision=view["revision"],idempotency_key=f"duo-{node_id}-{user.id}");self.assertEqual(response["validator_result"],"CORRECT");return response["view"]
    def test_two_seats_use_the_two_role_content_set(self):
        view=room_view(self.db,session_id=self.session.id,actor=self.players[0])
        self.assertEqual(view["rules_version"],"nadir2-v1");self.assertEqual(view["seat_count"],2);self.assertEqual(view["ai_consoles"],[])
        self.assertEqual({p["role"] for p in view["players"]},{"ENGINEER","NAVIGATOR"})
        self.assertEqual(next(n for n in view["nodes"] if n["id"]=="E0")["answer_format"],"2 rakam")
    def test_two_players_can_finish_the_room(self):
        self._solve("E0",self.players[0],"37");self._solve("P1",self.players[0],"A-C-F");self._solve("P2",self.players[1],"K4")
        self._solve("G1",self.players[0],"471");self._solve("G2",self.players[1],"SOL-SAG-SOL");self._solve("O1",self.players[1],"NADIR")
        self._solve("M1",self.players[0],"ION");view=self._solve("M1",self.players[1],"K4")
        self.assertEqual(next(n for n in view["nodes"] if n["id"]=="M1")["status"],"SOLVED")
        self.assertEqual(self.db.query(EscapeSimultaneousSubmission).count(),2)
        final=self._solve("F1",self.players[0],"ANAHTAR-MUHUR-UCUS");self.assertEqual(final["status"],"COMPLETED")


class EscapeRoomAiSeatTests(unittest.TestCase):
    """İki insan + AI üçüncü konsol: NADİR-3 içeriği aynen kullanılır."""
    def setUp(self):
        self.engine=create_engine("sqlite+pysqlite:///:memory:");Base.metadata.create_all(self.engine);self.Session=sessionmaker(bind=self.engine);self.db=self.Session()
        self.players=[User(username=f"ai-escape-{i}",email=f"ai-escape-{i}@test",hashed_password="x") for i in range(2)];self.db.add_all(self.players);self.db.flush()
        self.server=Server(name="NADIR ai",owner_id=self.players[0].id);self.db.add(self.server);self.db.flush();self.db.add_all([ServerMember(server_id=self.server.id,user_id=u.id) for u in self.players]);self.db.commit()
        self.session=create_room(self.db,server_id=self.server.id,actor=self.players[0],payload=EscapeCreate(player_ids=[u.id for u in self.players],ai_players=1),idempotency_key="ai-escape-001")
    def tearDown(self):self.db.close();self.engine.dispose()
    def _solve(self,node_id,user,answer):
        view=room_view(self.db,session_id=self.session.id,actor=user);node=next(n for n in view["nodes"] if n["id"]==node_id)
        self.assertIsNotNone(node["submit_token"],f"{node_id} gönderilemiyor")
        response=submit_answer(self.db,session_id=self.session.id,node_id=node_id,actor=user,answer=answer,token=node["submit_token"],revision=view["revision"],idempotency_key=f"ai-{node_id}-{user.id}");self.assertEqual(response["validator_result"],"CORRECT");return response["view"]
    def test_ai_console_shares_clues_and_holds_no_table_row(self):
        view=room_view(self.db,session_id=self.session.id,actor=self.players[0])
        self.assertEqual(view["rules_version"],"nadir3-v1");self.assertEqual(view["seat_count"],3)
        # AI konsolu escape_private_consoles tablosunda satır tutmaz.
        self.assertEqual(self.db.query(EscapePrivateConsole).filter_by(session_id=self.session.id).count(),2)
        ai_console=view["ai_consoles"][0];self.assertEqual(ai_console["role"],"NAVIGATOR")
        # Açık düğüm yalnız E0 olduğu için AI yalnız onun ipucunu paylaşır.
        self.assertEqual(set(ai_console["clues"]),{"E0"});self.assertEqual(ai_console["clues"]["E0"],"Son ışık değeri 7.")
    def test_humans_can_submit_the_ai_owned_puzzle_and_ai_completes_the_sync(self):
        self._solve("E0",self.players[0],"317");self._solve("P1",self.players[0],"A-C-F");self._solve("P2",self.players[1],"DELTA,BETA,ALFA,GAMA")
        # P3 NAVIGATOR'ün, yani AI'ın bulmacası; insan oyuncu gönderebilmeli.
        self._solve("P3",self.players[0],"K4")
        self._solve("G1",self.players[0],"471");self._solve("G2",self.players[1],"SOL-SAG-SOL")
        # M1: iki insan kendi kodunu girer, üçüncü kodu AI aynı anda gönderir.
        self._solve("M1",self.players[0],"ION");view=self._solve("M1",self.players[1],"47")
        self.assertEqual(next(n for n in view["nodes"] if n["id"]=="M1")["status"],"SOLVED")
        self.assertEqual(self.db.query(EscapeSimultaneousSubmission).count(),2)
        final=self._solve("F1",self.players[0],"ANAHTAR-MUHUR-UCUS");self.assertEqual(final["status"],"COMPLETED")


if __name__=="__main__":unittest.main()
