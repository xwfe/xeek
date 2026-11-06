//! 改一个条目的 UserName 并原样保存，用来和 KeePassXC 对照历史裁剪和合并。
//! 参考 helper 要求历史恰好多一份，裁剪时会报错，所以单独一个入口；只处理公开合成库。
use keepass::{
    db::{fields, EntryId},
    Database, DatabaseKey,
};
use std::{env, error::Error, fs, io};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().collect();
    // 可以给多个用户名：在同一个进程里依次编辑，用来制造同一秒内的连续修改。
    let [_, input, output, entry, usernames @ ..] = args.as_slice() else {
        return Err("usage: input output entry-uuid username...".into());
    };
    if usernames.is_empty() {
        return Err("usage: input output entry-uuid username...".into());
    }
    let mut password = String::new();
    io::stdin().read_line(&mut password)?;
    let key = DatabaseKey::new().with_password(password.trim_end_matches('\n'));
    let mut db = Database::parse(&fs::read(input)?, key.clone())?;
    let id = EntryId::from_uuid(entry.parse()?);
    for username in usernames {
        db.entry_mut(id)
            .ok_or("entry not found")?
            .edit_tracking(|tracked| tracked.set_unprotected(fields::USERNAME, username.as_str()));
    }
    let mut bytes = Vec::new();
    db.save(&mut bytes, key)?;
    fs::write(output, bytes)?;
    Ok(())
}
