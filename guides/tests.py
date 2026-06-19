from django.contrib.auth import get_user_model
from django.test import TestCase

from guides.models import LocalizationGuide
from guides.services import MAX_GUIDES, create_guide
from works.models import Work

User = get_user_model()


class GuideServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u', password='x')
        self.work = Work.objects.create(user=self.user, title='작품', genre='로맨스')

    def test_create_guide(self):
        guide = create_guide(self.work, 'JP', '가이드 내용')
        self.assertEqual(guide.target_country, 'JP')
        self.assertEqual(LocalizationGuide.objects.filter(work=self.work).count(), 1)

    def test_country_can_be_null(self):
        guide = create_guide(self.work, '', '국가 미정 가이드')
        self.assertIsNone(guide.target_country)

    def test_cap_keeps_only_latest_five(self):
        for i in range(7):
            create_guide(self.work, 'JP', f'가이드 {i}')
        self.assertEqual(
            LocalizationGuide.objects.filter(work=self.work).count(), MAX_GUIDES
        )
