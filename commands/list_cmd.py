"""list — list AWS resources by type, filter by tag / missing-tag.

WHAT YOU MUST BUILD
-------------------
Support 4 resource types: ec2, rds, s3, volume.
Each takes:
- `want` — list of (key, value) tag pairs the resource MUST have
- `missing` — list of tag keys the resource MUST NOT have

Print a formatted table to stdout. Test cases are in tests/test_list.py.

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)            # "Owner=alice" -> ("Owner", "alice")
  tags_to_dict(items) -> dict       # boto3 [{"Key","Value"}] -> {k: v}
  tags_match(tags, want, missing) -> bool

AWS APIS YOU'LL NEED
--------------------
- EC2: ec2.describe_instances() with get_paginator
- RDS: rds.describe_db_instances(), then list_tags_for_resource(ResourceName=arn)
- S3:  s3.list_buckets(), then get_bucket_tagging(Bucket=name)
       (catch ClientError when bucket has no tagging config — treat as {})
- EBS: ec2.describe_volumes() with get_paginator

EXPECTED OUTPUT FORMAT (when run from CLI)
------------------------------------------
    EC2 Environment=dev — 1 found:
    ------------------------------------------------------------------------------
      i-0abc123def456789a       t3.micro       running       Environment=dev

VERIFY
------
    pytest tests/test_list.py -v
"""
import boto3

from botocore.exceptions import ClientError

from commands._common import parse_kv, tags_to_dict, tags_match


def _list_ec2(want, missing):
    """List EC2 instances matching tag filters.

    Args:
        want: list of (key, value) tag pairs that must all match
        missing: list of tag keys that must NOT be present

    Returns:
        list of (instance_id, instance_type, state, tags_dict) tuples
    """
    ec2 = boto3.client("ec2")
    rows = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for res in page.get("Reservations", []):
            for inst in res.get("Instances", []):
                state = inst.get("State", {}).get("Name")
                # tests expect we ignore instances that are already gone
                if state in ("shutting-down", "terminated"):
                    continue
                iid = inst.get("InstanceId")
                itype = inst.get("InstanceType")
                tags = tags_to_dict(inst.get("Tags"))
                if tags_match(tags, want, missing):
                    rows.append((iid, itype, state, tags))
    return rows


def _list_rds(want, missing):
    """Same shape as _list_ec2 but for RDS DB instances.

    Note: RDS tags require a separate API call per DB:
        rds.list_tags_for_resource(ResourceName=db['DBInstanceArn'])

    Returns:
        list of (db_id, db_class, db_status, tags_dict) tuples
    """
    rds = boto3.client("rds")
    rows = []
    resp = rds.describe_db_instances()
    for db in resp.get("DBInstances", []):
        dbid = db.get("DBInstanceIdentifier")
        dbclass = db.get("DBInstanceClass")
        status = db.get("DBInstanceStatus")
        arn = db.get("DBInstanceArn")

        tags = {}
        try:
            tref = rds.list_tags_for_resource(ResourceName=arn)
            tags = tags_to_dict(tref.get("TagList"))
        except ClientError:
            tags = {}

        if tags_match(tags, want, missing):
            rows.append((dbid, dbclass, status, tags))
    return rows


def _list_s3(want, missing):
    """List S3 buckets matching tag filters.

    Note: get_bucket_tagging raises ClientError if no tagging config exists
    for that bucket. Treat that as an empty tags dict, not an error.

    Returns:
        list of (bucket_name, "bucket", "active", tags_dict) tuples
    """
    s3 = boto3.client("s3")
    rows = []
    for b in s3.list_buckets().get("Buckets", []):
        name = b.get("Name")
        tags = {}
        try:
            tref = s3.get_bucket_tagging(Bucket=name)
            tags = tags_to_dict(tref.get("TagSet"))
        except ClientError:
            # bucket has no tags -> treat as empty tags
            tags = {}
        if tags_match(tags, want, missing):
            rows.append((name, "bucket", "active", tags))
    return rows


def _list_volume(want, missing):
    """List EBS volumes matching tag filters.

    Returns:
        list of (volume_id, "<type>-<size>GB", state, tags_dict) tuples
        e.g. ("vol-0abc", "gp2-100GB", "in-use", {"purpose": "practice"})
    """
    ec2 = boto3.client("ec2")
    rows = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate():
        for vol in page.get("Volumes", []):
            vid = vol.get("VolumeId")
            vtype = f"{vol.get('VolumeType')}-{vol.get('Size')}GB"
            state = vol.get("State")
            tags = tags_to_dict(vol.get("Tags"))
            if tags_match(tags, want, missing):
                rows.append((vid, vtype, state, tags))
    return rows


DISPATCH = {
    "ec2": _list_ec2,
    "rds": _list_rds,
    "s3": _list_s3,
    "volume": _list_volume,
}


def run(args):
    """Entry point called by costctl.py.

    Steps you should perform:
      1. Convert args.tag (list of "k=v" strings) → want pairs via parse_kv
      2. Use args.missing_tag (list of keys) as-is
      3. Call DISPATCH[args.type](want, missing) → rows
      4. Print a header line, separator, then one row per resource

    Args set by argparse:
        args.type         — one of "ec2", "rds", "s3", "volume"
        args.tag          — list[str], each "key=value"
        args.missing_tag  — list[str], each "key"
    """
    want = [parse_kv(s) for s in (args.tag or [])]
    missing = args.missing_tag or []
    rows = DISPATCH[args.type](want, missing)

    type_label = args.type.upper()
    if want:
        filt = " ".join(f"{k}={v}" for k, v in want)
    elif missing:
        filt = "missing:" + ",".join(missing)
    else:
        filt = "no filter"

    print(f"{type_label} {filt} — {len(rows)} found:")
    print("-" * 78)
    for ident, desc, state, tags in rows:
        tagstr = " ".join(f"{k}={v}" for k, v in tags.items()) if tags else "(no tags)"
        print(f"  {ident:20}  {desc:12}  {state:12}  {tagstr}")
