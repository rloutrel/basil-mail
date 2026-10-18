from django.core.management.base import BaseCommand

from mails.imap import run_fetch
from mails.models import MailSource


class Command(BaseCommand):
    help = "Fetch new mails from every enabled source whose interval has elapsed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            dest="source",
            help="Only fetch the source with this name or pk.",
        )

    def handle(self, *args, **options):
        qs = MailSource.objects.all()
        if options["source"]:
            qs = qs.filter(name=options["source"]) | qs.filter(pk=options["source"])
        results = run_fetch(source_qs=qs)
        if not results:
            self.stdout.write(self.style.WARNING("Nothing to fetch."))
            return
        for name, res in results.items():
            if "error" in res:
                self.stdout.write(
                    self.style.ERROR("%s: failed (%s)" % (name, res["error"]))
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("%s: %d new mail(s)" % (name, res["new"]))
                )
