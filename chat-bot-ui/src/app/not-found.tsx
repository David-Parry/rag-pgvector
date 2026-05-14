import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function NotFoundPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <Card className="max-w-lg border-border/70 shadow-sm">
        <CardContent className="space-y-4 pt-6 text-center">
          <div className="space-y-2">
            <p className="font-semibold text-foreground text-lg">Page not found</p>
            <p className="text-muted-foreground text-sm">
              This chat UI route does not exist. Return to the main chat page to continue.
            </p>
          </div>
          <Link className={buttonVariants({ variant: "outline" })} href="/">
            Back to chat
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
