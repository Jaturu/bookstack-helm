<?php
// Wait until the database accepts a login, so migrations do not start against
// a server that is still initialising. The chart runs this with `php -r`; it
// reads the same DB_* environment as BookStack.
//
// Retries connection failures until WAIT_TIMEOUT seconds have passed. Fails at
// once on errors that waiting cannot fix: bad credentials or a missing database.

$timeout = (int) (getenv('WAIT_TIMEOUT') ?: 300);
$deadline = time() + $timeout;
$host = getenv('DB_HOST') ?: 'localhost';
$port = getenv('DB_PORT') ?: '3306';
$name = getenv('DB_DATABASE') ?: '';
$dsn = "mysql:host={$host};port={$port};dbname={$name}";

// MySQL/MariaDB server error codes that are permanent.
$fatal = [
    1044 => 'access denied to the database',
    1045 => 'access denied (check the username and password)',
    1049 => 'unknown database',
];

$attempt = 0;
$last = '';
while (true) {
    $attempt++;
    try {
        new PDO($dsn, getenv('DB_USERNAME') ?: '', getenv('DB_PASSWORD') ?: '', [
            PDO::ATTR_TIMEOUT => 5,
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        ]);
        fwrite(STDOUT, "database {$host}:{$port}/{$name} is ready (attempt {$attempt})\n");
        exit(0);
    } catch (PDOException $e) {
        $code = (int) ($e->errorInfo[1] ?? 0);
        if (isset($fatal[$code])) {
            fwrite(STDERR, "database {$host}:{$port}/{$name}: {$fatal[$code]}: {$e->getMessage()}\n");
            exit(1);
        }
        // Log the first failure, any change, and every 15th attempt (~30 s).
        $message = $e->getMessage();
        if ($message !== $last || $attempt % 15 === 1) {
            fwrite(STDERR, "waiting for database {$host}:{$port}: {$message}\n");
            $last = $message;
        }
    }
    if (time() >= $deadline) {
        fwrite(STDERR, "database {$host}:{$port} not ready after {$timeout}s, giving up\n");
        exit(1);
    }
    sleep(2);
}
