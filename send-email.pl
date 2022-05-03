#!/usr/bin/env perl
use Modern::Perl;
use Email::Send::SMTP::Gmail;
use Nice::Try;



try {
  my $header  = `cat header.html`;
  my $rows = `cat new_filings.sql | sqlite3 -html -header filings.sqlite`;
  my $update = `cat update_query.sql | sqlite3 filings.sqlite`;
  my $emails = 'wrmorris2@registermedia.com,
                metroia@registermedia.com,
                pjoens@registermedia.com, 
                dlathrop@registermedia.com,
                asahouri@registermedia.com,
                ccrowder@registermedia.com';

  my $message = "$header\n$rows\n</table>";
  my ( $smtp, $error ) = Email::Send::SMTP::Gmail->new( 
                                      -smtp    => 'smtp.gmail.com',
                                      -login   => $ENV{'GMAIL_USER'},
                                      -pass    => $ENV{'GMAIL_PWD'});

  print "session error: $error" unless ($smtp!=-1);


  $smtp->send(
    -to=>$emails,
    -subject=>'Court bot results', 
    -body=>"<html><head></head>
      <body>
      <p>Recent filings</p>
      $message
      <p>
      <small>Brought to you by Daniel Lathrop and the letter p.</small></p>
      </body>
      </html>",
    -contenttype => 'text/html');

  $smtp->bye;
} catch ($e) {
  say "SQLite Query or e-mail failed";
}


