from django.contrib.auth import get_user_model
from django.test import TestCase

from translation.models import ChatMessage, TranslationResult
from translation.services import (
    MAX_VERSIONS,
    apply_chat_edit,
    create_translation_version,
    source_unchanged,
)
from works.models import Episode, Work

User = get_user_model()


class TranslationVersionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')
        self.work = Work.objects.create(user=self.user, title='작품', genre='판타지')
        self.episode = Episode.objects.create(
            work=self.work, title='1화', episode_no=1, original_text='원문 v1'
        )

    def _run(self, text='번역본'):
        return create_translation_version(
            episode=self.episode, target_country='JP', translated_text=text
        )

    def test_first_run_creates_version_1(self):
        version, created = self._run()
        self.assertTrue(created)
        self.assertEqual(version.version_no, 1)
        self.assertEqual(version.original_text, '원문 v1')

    def test_unchanged_source_does_not_create_new_version(self):
        self._run()
        version, created = self._run('다시 번역')
        self.assertFalse(created)
        self.assertEqual(version.version_no, 1)
        self.assertTrue(source_unchanged(self.episode, 'JP'))
        self.assertEqual(
            TranslationResult.objects.filter(episode=self.episode).count(), 1
        )

    def test_changed_source_creates_new_version(self):
        self._run()
        self.episode.original_text = '원문 v2'
        self.episode.save(update_fields=['original_text'])
        version, created = self._run()
        self.assertTrue(created)
        self.assertEqual(version.version_no, 2)

    def test_cap_keeps_only_latest_three(self):
        for i in range(1, 5):  # 4개 버전 시도 → 최신 3개만 유지
            self.episode.original_text = f'원문 v{i}'
            self.episode.save(update_fields=['original_text'])
            self._run(f'번역 {i}')
        versions = TranslationResult.objects.filter(
            episode=self.episode, target_country='JP'
        ).order_by('version_no')
        self.assertEqual(versions.count(), MAX_VERSIONS)
        self.assertEqual(list(versions.values_list('version_no', flat=True)), [2, 3, 4])

    def test_per_country_independent_versions(self):
        self._run()
        v_us, created = create_translation_version(
            episode=self.episode, target_country='US', translated_text='en'
        )
        self.assertTrue(created)
        self.assertEqual(v_us.version_no, 1)

    def test_apply_chat_edit_updates_current_no_new_version(self):
        version, _ = self._run('초기 번역')
        apply_chat_edit(version, '수정된 번역')
        version.refresh_from_db()
        self.assertEqual(version.translated_text, '수정된 번역')
        self.assertEqual(version.final_text, '수정된 번역')
        self.assertEqual(
            TranslationResult.objects.filter(episode=self.episode).count(), 1
        )

    def test_chat_message_persists(self):
        version, _ = self._run()
        ChatMessage.objects.create(
            translation=version,
            sender_type=ChatMessage.SENDER_USER,
            message_text='왜 이렇게 번역했어?',
        )
        self.assertEqual(version.chat_messages.count(), 1)
